from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field

from retrieval_lab.generation.citations import Citation, parse_citations
from retrieval_lab.generation.prompt import build_answer_request
from retrieval_lab.llm.base import ABSTAIN_TOKEN, LLMProvider, TokenUsage
from retrieval_lab.retrieval.config import GenerationSettings
from retrieval_lab.retrieval.pipeline import RetrievalPipeline
from retrieval_lab.retrieval.types import RetrievalOutcome

AbstainReason = Literal["no_results", "low_evidence", "model_declined"]

ABSTAIN_MESSAGES: dict[AbstainReason, str] = {
    "no_results": "Nothing in the library matched this question.",
    "low_evidence": "The best evidence found was too weak to answer reliably.",
    "model_declined": "The retrieved passages do not contain the answer.",
}


class Answer(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    invalid_markers: list[int] = Field(default_factory=list)
    abstained: bool = False
    abstain_reason: AbstainReason | None = None
    top_evidence_score: float | None = None
    model: str | None = None


class QueryResult(BaseModel):
    question: str
    answer: Answer
    retrieval: RetrievalOutcome
    timings_ms: dict[str, float]
    usage: dict[str, TokenUsage]

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usage.values())


class AnswerService:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def answer(
        self, question: str, pipeline: RetrievalPipeline, *, generate: bool = True, top_k: int | None = None
    ) -> QueryResult:
        started = time.perf_counter()
        retrieval = await pipeline.retrieve(question, top_k=top_k)
        settings = pipeline.spec.generation
        timings = dict(retrieval.timings_ms)
        usage = dict(retrieval.usage)

        if generate:
            answer = await self._generate(question, retrieval, settings, timings, usage)
        else:
            answer = Answer(text="", top_evidence_score=_top_score(retrieval))
        timings["total"] = round((time.perf_counter() - started) * 1000, 3)
        return QueryResult(
            question=question, answer=answer, retrieval=retrieval, timings_ms=timings, usage=usage
        )

    async def _generate(
        self,
        question: str,
        retrieval: RetrievalOutcome,
        settings: GenerationSettings,
        timings: dict[str, float],
        usage: dict[str, TokenUsage],
    ) -> Answer:
        top_score = _top_score(retrieval)
        if not retrieval.chunks:
            return _abstain("no_results", top_score)
        if settings.abstain_below is not None and (top_score or 0.0) < settings.abstain_below:
            return _abstain("low_evidence", top_score)

        context = retrieval.chunks[: settings.max_context_chunks]
        request = build_answer_request(question, context, settings.max_output_tokens)
        generate_started = time.perf_counter()
        response = await self._llm.complete(request)
        timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 3)
        usage["generate"] = response.usage

        if response.text.strip().startswith(ABSTAIN_TOKEN):
            return _abstain("model_declined", top_score, model=response.model)
        parsed = parse_citations(response.text, context)
        return Answer(
            text=response.text.strip(),
            citations=parsed.citations,
            invalid_markers=parsed.invalid_markers,
            top_evidence_score=top_score,
            model=response.model,
        )


def _top_score(retrieval: RetrievalOutcome) -> float | None:
    return retrieval.chunks[0].evidence_score if retrieval.chunks else None


def _abstain(reason: AbstainReason, top_score: float | None, model: str | None = None) -> Answer:
    return Answer(
        text=ABSTAIN_MESSAGES[reason],
        abstained=True,
        abstain_reason=reason,
        top_evidence_score=top_score,
        model=model,
    )
