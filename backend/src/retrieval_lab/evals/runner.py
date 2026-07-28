from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from retrieval_lab.db.models import EvalRun, GoldenQuestion
from retrieval_lab.db.session import transaction
from retrieval_lab.errors import ValidationFailedError
from retrieval_lab.evals import metrics
from retrieval_lab.evals.evidence import locate
from retrieval_lab.evals.judge import Judge
from retrieval_lab.evals.schemas import (
    AggregateMetrics,
    ExpectedChunk,
    LatencyStats,
    QuestionMetrics,
    QuestionResult,
    RetrievedRecord,
    RunEnvironment,
    RunMode,
    RunSummary,
    RunTrigger,
    StageCost,
)
from retrieval_lab.generation.service import AnswerService
from retrieval_lab.llm.base import TokenUsage
from retrieval_lab.log import get_logger
from retrieval_lab.repositories.chunks import ChunkRepository, ChunkSpan
from retrieval_lab.repositories.configs import ConfigRepository, spec_of
from retrieval_lab.repositories.documents import DocumentRepository
from retrieval_lab.repositories.golden import GoldenRepository
from retrieval_lab.repositories.runs import RunRepository
from retrieval_lab.retrieval.components import IndexGuard
from retrieval_lab.retrieval.config import AnyPipeline
from retrieval_lab.retrieval.pipeline import RetrievalPipeline

log = get_logger(__name__)

PipelineBuilder = Callable[[AnyPipeline], RetrievalPipeline]


@dataclass(frozen=True, slots=True)
class _Evidence:
    spans: list[metrics.Span]
    pool: list[metrics.Span]
    pool_ids: dict[metrics.Span, str]


def golden_hash(questions: Sequence[GoldenQuestion]) -> str:
    """Content hash of the accepted golden set; row ids differ per database, so they are left out."""
    rows = sorted((q.question, q.document_slug or "", q.evidence or "", q.answerable) for q in questions)
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


class EvalRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        build_pipeline: PipelineBuilder,
        answers: AnswerService,
        judge: Judge,
        index_guard: IndexGuard,
        *,
        llm_model: str,
        embedding_model: str,
        reranker_model: str,
        concurrency: int = 4,
    ) -> None:
        self._sessions = sessions
        self._build_pipeline = build_pipeline
        self._answers = answers
        self._judge = judge
        self._index_guard = index_guard
        self._llm_model = llm_model
        self._embedding_model = embedding_model
        self._reranker_model = reranker_model
        self._concurrency = concurrency

    async def start(
        self,
        config_ref: str,
        *,
        mode: RunMode = "full",
        trigger: RunTrigger = "api",
        label: str | None = None,
        k: int | None = None,
    ) -> EvalRun:
        async with transaction(self._sessions) as session:
            config = await ConfigRepository(session).resolve(config_ref)
            questions = await GoldenRepository(session).accepted()
            if not questions:
                raise ValidationFailedError(
                    "The golden set has no accepted questions; seed or review some first"
                )
            run = await RunRepository(session).create(
                config_id=config.id,
                mode=mode,
                trigger=trigger,
                label=label,
                k=k or spec_of(config).top_k,
                question_count=len(questions),
                llm_model=self._llm_model if mode == "full" else "none",
                judge_model=self._judge.model if mode == "full" else "none",
            )
        log.info("eval_run_created", run_id=str(run.id), config=config.name, version=config.version)
        return run

    async def execute(self, run_id: uuid.UUID) -> RunSummary:
        try:
            return await self._execute(run_id)
        except asyncio.CancelledError:
            async with transaction(self._sessions) as session:
                await RunRepository(session).fail(run_id, "Cancelled: the service shut down mid-run")
            raise
        except Exception as exc:
            log.exception("eval_run_failed", run_id=str(run_id))
            cause = _first_cause(exc)
            async with transaction(self._sessions) as session:
                await RunRepository(session).fail(run_id, f"{type(cause).__name__}: {cause}")
            raise

    async def run(
        self,
        config_ref: str,
        *,
        mode: RunMode = "full",
        trigger: RunTrigger = "cli",
        label: str | None = None,
        k: int | None = None,
    ) -> tuple[EvalRun, RunSummary]:
        run = await self.start(config_ref, mode=mode, trigger=trigger, label=label, k=k)
        summary = await self.execute(run.id)
        async with self._sessions() as session:
            return await RunRepository(session).get(run.id), summary

    async def _execute(self, run_id: uuid.UUID) -> RunSummary:
        await self._index_guard.check()
        async with transaction(self._sessions) as session:
            runs = RunRepository(session)
            run = await runs.get(run_id)
            await runs.mark_running(run_id)
            spec = spec_of(run.config)
            questions = await GoldenRepository(session).accepted()
            evidence = await self._resolve_evidence(session, questions)

        pipeline = self._build_pipeline(spec)
        mode: RunMode = "full" if run.mode == "full" else "retrieval"
        semaphore = asyncio.Semaphore(self._concurrency)

        async def one(question: GoldenQuestion) -> None:
            async with semaphore:
                result = await self._evaluate(question, evidence.get(question.id), pipeline, run.k, mode)
            async with transaction(self._sessions) as session:
                await RunRepository(session).add_result(
                    run_id, question.id, result.metrics.ndcg_at_k, result.model_dump(mode="json")
                )

        # A TaskGroup cancels the remaining questions as soon as one fails, so a failed run
        # stops spending tokens instead of finishing in the background.
        async with asyncio.TaskGroup() as group:
            for question in questions:
                group.create_task(one(question))

        environment = RunEnvironment(
            llm_model=run.llm_model,
            judge_model=run.judge_model,
            embedding_model=self._embedding_model,
            reranker_model=self._reranker_model,
            golden_hash=golden_hash(questions),
        )
        async with transaction(self._sessions) as session:
            runs = RunRepository(session)
            stored = [QuestionResult.model_validate(r.payload) for r in await runs.all_results(run_id)]
            summary = summarize(stored, k=run.k, mode=mode, environment=environment)
            await runs.finish(run_id, summary.model_dump(mode="json"))
        log.info(
            "eval_run_completed",
            run_id=str(run_id),
            ndcg=summary.metrics.ndcg_at_k,
            faithfulness=summary.metrics.faithfulness,
        )
        return summary

    async def _resolve_evidence(
        self, session: AsyncSession, questions: Sequence[GoldenQuestion]
    ) -> dict[uuid.UUID, _Evidence]:
        slugs = sorted({q.document_slug for q in questions if q.document_slug and q.answerable})
        contents = await DocumentRepository(session).contents(slugs)
        chunk_spans = await ChunkRepository(session).spans_for_documents(slugs)
        resolved: dict[uuid.UUID, _Evidence] = {}
        for question in questions:
            if not (question.answerable and question.evidence and question.document_slug):
                continue
            content = contents.get(question.document_slug)
            located = locate(content, question.evidence) if content else None
            if located is None:
                log.warning("evidence_not_found", question_id=str(question.id), slug=question.document_slug)
                continue
            span = metrics.Span(question.document_slug, *located)
            pool_ids = {
                _span(question.document_slug, c): c.id
                for c in chunk_spans.get(question.document_slug, [])
                if c.char_start < span.end and c.char_end > span.start
            }
            resolved[question.id] = _Evidence([span], list(pool_ids), pool_ids)
        return resolved

    async def _evaluate(
        self,
        question: GoldenQuestion,
        evidence: _Evidence | None,
        pipeline: RetrievalPipeline,
        k: int,
        mode: RunMode,
    ) -> QuestionResult:
        result = await self._answers.answer(question.question, pipeline, generate=mode == "full", top_k=k)
        chunks = result.retrieval.chunks
        ranked = [metrics.Span(c.document_slug, c.char_start, c.char_end) for c in chunks]
        scores = QuestionMetrics()
        retrieved: list[RetrievedRecord] = []
        expected: list[ExpectedChunk] = []

        spans = evidence.spans if evidence else []
        for chunk, span in zip(chunks, ranked, strict=True):
            retrieved.append(
                RetrievedRecord(
                    chunk_id=chunk.chunk_id,
                    rank=chunk.rank,
                    document_slug=chunk.document_slug,
                    heading=chunk.heading,
                    score=chunk.score,
                    evidence_score=chunk.evidence_score,
                    coverage=round(metrics.coverage(spans, [span]), 4) if spans else 0.0,
                    relevant=metrics.is_relevant(spans, span) if spans else False,
                    stage_ranks=chunk.stage_ranks,
                )
            )
        if evidence is not None:
            expected = [
                ExpectedChunk(chunk_id=chunk_id, coverage=round(metrics.coverage(spans, [span]), 4))
                for span, chunk_id in evidence.pool_ids.items()
            ]
            scores.recall_at_k = metrics.recall_at_k(spans, ranked, k)
            scores.mrr = metrics.reciprocal_rank(spans, ranked, k)
            scores.ndcg_at_k = metrics.ndcg_at_k(spans, ranked, evidence.pool, k)

        usage = dict(result.usage)
        claims = []
        relevance_reason = None
        if mode == "full":
            answer = result.answer
            scores.abstained = answer.abstained
            if not question.answerable:
                scores.correct_abstention = answer.abstained
            answered = not answer.abstained
            context_limit = pipeline.spec.generation.max_context_chunks
            contexts = [c.content for c in chunks[:context_limit]]
            faith, relevance, usefulness = await asyncio.gather(
                _maybe(
                    self._judge.faithfulness(question.question, answer.text, contexts) if answered else None
                ),
                _maybe(self._judge.relevance(question.question, answer.text) if answered else None),
                _maybe(
                    self._judge.context_usefulness(
                        question.question, _reference(question), [c.content for c in chunks[:k]]
                    )
                    if evidence is not None and chunks
                    else None
                ),
            )
            judge_usage = TokenUsage()
            if usefulness is not None:
                scores.context_precision = usefulness.precision
                judge_usage += usefulness.usage
                retrieved = [
                    record.model_copy(update={"useful": flag})
                    for record, flag in zip(retrieved, usefulness.useful, strict=True)
                ]
            if faith is not None and relevance is not None:
                scores.faithfulness = faith.score
                scores.answer_relevance = relevance.score
                claims = faith.verdict.claims
                relevance_reason = relevance.verdict.reason
                judge_usage += faith.usage + relevance.usage
                relevant_ids = {r.chunk_id for r in retrieved if r.coverage > 0}
                if evidence is not None and answer.citations:
                    hits = sum(c.chunk_id in relevant_ids for c in answer.citations)
                    scores.citation_accuracy = hits / len(answer.citations)
            if judge_usage.input_tokens or judge_usage.output_tokens:
                usage["judge"] = judge_usage

        return QuestionResult(
            question_id=str(question.id),
            question=question.question,
            answerable=question.answerable,
            document_slug=question.document_slug,
            evidence=question.evidence,
            evidence_found=evidence is not None,
            expected=expected,
            retrieved=retrieved,
            rewritten_query=result.retrieval.rewritten_query,
            metrics=scores,
            answer=result.answer.text if mode == "full" else None,
            abstain_reason=result.answer.abstain_reason,
            citations=result.answer.citations,
            claims=claims,
            relevance_reason=relevance_reason,
            timings_ms=result.timings_ms,
            usage=usage,
        )


async def _maybe[T](call: Awaitable[T] | None) -> T | None:
    return None if call is None else await call


def _reference(question: GoldenQuestion) -> str:
    parts = [question.reference_answer or "", question.evidence or ""]
    return "\n".join(p for p in parts if p)


def _first_cause(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _span(slug: str, chunk: ChunkSpan) -> metrics.Span:
    return metrics.Span(slug, chunk.char_start, chunk.char_end)


def _avg(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    value = metrics.mean(present)
    return None if value is None else round(value, 4)


def summarize(
    results: Sequence[QuestionResult],
    *,
    k: int,
    mode: RunMode,
    environment: RunEnvironment | None = None,
) -> RunSummary:
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    scored = [r.metrics for r in answerable if r.evidence_found]
    full = mode == "full"
    aggregate = AggregateMetrics(
        recall_at_k=_avg([m.recall_at_k for m in scored]),
        mrr=_avg([m.mrr for m in scored]),
        ndcg_at_k=_avg([m.ndcg_at_k for m in scored]),
        context_precision=_avg([m.context_precision for m in scored]),
        faithfulness=_avg([r.metrics.faithfulness for r in results]) if full else None,
        answer_relevance=_avg([r.metrics.answer_relevance for r in answerable]) if full else None,
        citation_accuracy=_avg([m.citation_accuracy for m in scored]) if full else None,
        abstention_accuracy=(
            _avg([float(bool(r.metrics.correct_abstention)) for r in unanswerable]) if full else None
        ),
        false_abstention_rate=_avg([float(r.metrics.abstained) for r in answerable]) if full else None,
    )

    timings: dict[str, list[float]] = defaultdict(list)
    costs: dict[str, TokenUsage] = defaultdict(TokenUsage)
    for result in results:
        for stage, ms in result.timings_ms.items():
            timings[stage].append(ms)
        for stage, used in result.usage.items():
            costs[stage] = costs[stage] + used
    latency = {
        stage: LatencyStats(
            p50=round(metrics.percentile(values, 0.5), 2),
            p95=round(metrics.percentile(values, 0.95), 2),
            mean=round(sum(values) / len(values), 2),
        )
        for stage, values in sorted(timings.items())
    }
    cost = {
        stage: StageCost(
            input_tokens=u.input_tokens, output_tokens=u.output_tokens, cost_usd=round(u.cost_usd, 6)
        )
        for stage, u in sorted(costs.items())
    }
    total = sum(c.cost_usd for c in cost.values())
    return RunSummary(
        k=k,
        mode=mode,
        environment=environment,
        question_count=len(results),
        answerable_count=len(answerable),
        unanswerable_count=len(unanswerable),
        metrics=aggregate,
        latency_ms=latency,
        cost=cost,
        total_cost_usd=round(total, 6),
        cost_per_query_usd=round(total / len(results), 6) if results else 0.0,
    )
