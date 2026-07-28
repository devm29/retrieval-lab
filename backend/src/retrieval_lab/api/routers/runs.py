from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from retrieval_lab.api.deps import ContainerDep, PaginationDep, SchedulerDep, SessionDep
from retrieval_lab.api.mappers import config_out, run_out
from retrieval_lab.api.schemas import (
    BaselineIn,
    CompareOut,
    ExpectedChunkOut,
    LeaderboardRow,
    Page,
    QuestionDelta,
    ResultDetail,
    ResultRow,
    RetrievedChunkOut,
    RunCreate,
    RunOut,
)
from retrieval_lab.db.models import EvalRun, RunStatus
from retrieval_lab.db.session import transaction
from retrieval_lab.errors import ConflictError, ValidationFailedError
from retrieval_lab.evals.baseline import compare
from retrieval_lab.evals.evidence import locate
from retrieval_lab.evals.schemas import GateResult, GateTolerance, QuestionResult, RunSummary
from retrieval_lab.repositories.chunks import ChunkRepository
from retrieval_lab.repositories.configs import spec_of
from retrieval_lab.repositories.documents import DocumentRepository
from retrieval_lab.repositories.runs import ResultSort, RunRepository

router = APIRouter(tags=["runs"])


def _summary(run: EvalRun) -> RunSummary:
    if run.status is not RunStatus.COMPLETED or not run.summary:
        raise ConflictError(f"Run {run.id} has not completed")
    return RunSummary.model_validate(run.summary)


def _gate(baseline: EvalRun, candidate: EvalRun, tolerance: GateTolerance) -> GateResult:
    return compare(
        _summary(baseline),
        _summary(candidate),
        tolerance,
        config_name=candidate.config.name,
        baseline_label=f"{baseline.config.name}@{baseline.config.version} · {str(baseline.id)[:8]}",
        candidate_label=f"{candidate.config.name}@{candidate.config.version} · {str(candidate.id)[:8]}",
        spec_hashes=(baseline.config.spec_hash, candidate.config.spec_hash),
    )


@router.get("/runs")
async def list_runs(
    session: SessionDep,
    pagination: PaginationDep,
    config: str | None = None,
    status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
) -> Page[RunOut]:
    repo = RunRepository(session)
    runs, total = await repo.page(
        config_name=config, status=status_filter, offset=pagination.offset, limit=pagination.page_size
    )
    baselines = set((await repo.baselines()).values())
    return Page(
        items=[run_out(r, is_baseline=r.id in baselines) for r in runs],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_run(body: RunCreate, container: ContainerDep, scheduler: SchedulerDep) -> RunOut:
    with scheduler.reserve():
        run = await container.runner.start(
            body.config, mode=body.mode, trigger="api", label=body.label, k=body.k
        )
        scheduler.submit(run.id)
    return run_out(run)


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, session: SessionDep) -> RunOut:
    repo = RunRepository(session)
    run = await repo.get(run_id)
    return run_out(run, is_baseline=run.id in set((await repo.baselines()).values()))


@router.get("/runs/{run_id}/results")
async def list_results(
    run_id: uuid.UUID,
    session: SessionDep,
    pagination: PaginationDep,
    sort: ResultSort = "ndcg_asc",
) -> Page[ResultRow]:
    repo = RunRepository(session)
    await repo.get(run_id)
    rows, total = await repo.results_page(
        run_id, sort=sort, offset=pagination.offset, limit=pagination.page_size
    )
    items: list[ResultRow] = []
    for row in rows:
        result = QuestionResult.model_validate(row.payload)
        items.append(
            ResultRow(
                question_id=row.question_id,
                external_id=row.question.external_id,
                question=result.question,
                answerable=result.answerable,
                document_slug=result.document_slug,
                metrics=result.metrics,
                abstain_reason=result.abstain_reason,
                total_ms=result.timings_ms.get("total"),
            )
        )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


def _highlight(span: tuple[int, int] | None, start: int, end: int) -> tuple[int, int] | None:
    if span is None or span[0] >= end or span[1] <= start:
        return None
    return max(span[0], start) - start, min(span[1], end) - start


@router.get("/runs/{run_id}/results/{question_id}")
async def result_detail(run_id: uuid.UUID, question_id: uuid.UUID, session: SessionDep) -> ResultDetail:
    runs = RunRepository(session)
    run = await runs.get(run_id)
    row = await runs.result(run_id, question_id)
    result = QuestionResult.model_validate(row.payload)

    ids = [r.chunk_id for r in result.retrieved] + [e.chunk_id for e in result.expected]
    views = await ChunkRepository(session).fetch(list(dict.fromkeys(ids)))
    span: tuple[int, int] | None = None
    if result.document_slug and result.evidence:
        contents = await DocumentRepository(session).contents([result.document_slug])
        if result.document_slug in contents:
            span = locate(contents[result.document_slug], result.evidence)

    retrieved: list[RetrievedChunkOut] = []
    for record in result.retrieved:
        view = views.get(record.chunk_id)
        same_doc = view is not None and view.document_slug == result.document_slug
        retrieved.append(
            RetrievedChunkOut(
                chunk_id=record.chunk_id,
                rank=record.rank,
                document_slug=record.document_slug,
                document_title=view.document_title if view else record.document_slug,
                heading=record.heading,
                content=view.content if view else None,
                score=record.score,
                evidence_score=record.evidence_score,
                coverage=record.coverage,
                relevant=record.relevant,
                stage_ranks=record.stage_ranks,
                highlight=_highlight(span, view.char_start, view.char_end) if view and same_doc else None,
            )
        )
    ranks = {r.chunk_id: r.rank for r in result.retrieved}
    expected = [
        ExpectedChunkOut(
            chunk_id=e.chunk_id,
            coverage=e.coverage,
            retrieved_rank=ranks.get(e.chunk_id),
            heading=views[e.chunk_id].heading if e.chunk_id in views else None,
            content=views[e.chunk_id].content if e.chunk_id in views else None,
            highlight=(
                _highlight(span, views[e.chunk_id].char_start, views[e.chunk_id].char_end)
                if e.chunk_id in views
                else None
            ),
        )
        for e in sorted(result.expected, key=lambda e: -e.coverage)
    ]
    spec = spec_of(run.config)
    return ResultDetail(
        run_id=run.id,
        config_name=run.config.name,
        k=run.k,
        max_context_chunks=spec.generation.max_context_chunks,
        rewrite_applies_to=spec.query_rewrite.apply_to if spec.query_rewrite else None,
        result=result,
        retrieved=retrieved,
        expected=expected,
    )


@router.get("/runs/{run_id}/gate")
async def run_gate(
    run_id: uuid.UUID,
    session: SessionDep,
    baseline_run: uuid.UUID | None = None,
    tolerance_ndcg: Annotated[float, Query(ge=0)] = 0.02,
    tolerance_faithfulness: Annotated[float, Query(ge=0)] = 0.03,
) -> GateResult:
    repo = RunRepository(session)
    candidate = await repo.get(run_id)
    baseline = (
        await repo.get(baseline_run) if baseline_run else await repo.baseline_for(candidate.config.name)
    )
    if baseline is None:
        raise ValidationFailedError(f"No baseline has been promoted for '{candidate.config.name}'")
    return _gate(
        baseline, candidate, GateTolerance(ndcg_at_k=tolerance_ndcg, faithfulness=tolerance_faithfulness)
    )


@router.get("/compare")
async def compare_runs(baseline: uuid.UUID, candidate: uuid.UUID, session: SessionDep) -> CompareOut:
    repo = RunRepository(session)
    before, after = await repo.get(baseline), await repo.get(candidate)
    gate = _gate(before, after, GateTolerance())
    before_scores = {r.question_id: r.ndcg for r in await repo.all_results(before.id)}
    deltas: list[QuestionDelta] = []
    for row in await repo.all_results(after.id):
        old = before_scores.get(row.question_id)
        deltas.append(
            QuestionDelta(
                question_id=row.question_id,
                question=row.question.question,
                baseline_ndcg=old,
                candidate_ndcg=row.ndcg,
                delta=None if old is None or row.ndcg is None else round(row.ndcg - old, 4),
            )
        )
    deltas.sort(key=lambda d: (d.delta is None, d.delta or 0.0))
    baselines = set((await repo.baselines()).values())
    return CompareOut(
        baseline=run_out(before, is_baseline=before.id in baselines),
        candidate=run_out(after, is_baseline=after.id in baselines),
        gate=gate,
        questions=deltas,
    )


@router.post("/baselines", status_code=status.HTTP_201_CREATED)
async def promote_baseline(body: BaselineIn, container: ContainerDep) -> RunOut:
    async with transaction(container.sessions) as session:
        repo = RunRepository(session)
        run = await repo.get(body.run_id)
        summary = _summary(run)
        if summary.mode != "full":
            raise ValidationFailedError("Only full runs (with generation metrics) can become a baseline")
        await repo.set_baseline(run.config.name, run.id)
    return run_out(run, is_baseline=True)


@router.get("/leaderboard")
async def leaderboard(session: SessionDep) -> list[LeaderboardRow]:
    repo = RunRepository(session)
    baseline_ids = await repo.baselines()
    baseline_runs = await repo.get_many(list(baseline_ids.values()))
    rows: list[LeaderboardRow] = []
    for run in await repo.latest_completed_per_config():
        summary = _summary(run)
        baseline_id = baseline_ids.get(run.config.name)
        baseline = baseline_runs.get(baseline_id) if baseline_id else None
        total = summary.latency_ms.get("total")
        rows.append(
            LeaderboardRow(
                config=config_out(run.config),
                run_id=run.id,
                finished_at=run.finished_at,
                metrics=summary.metrics,
                p50_ms=total.p50 if total else None,
                p95_ms=total.p95 if total else None,
                cost_per_query_usd=summary.cost_per_query_usd,
                gate=_gate(baseline, run, GateTolerance()) if baseline else None,
                is_baseline=baseline is not None and baseline.id == run.id,
            )
        )
    rows.sort(key=lambda r: -(r.metrics.ndcg_at_k or 0.0))
    return rows
