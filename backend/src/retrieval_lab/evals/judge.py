from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from retrieval_lab.errors import ProviderError
from retrieval_lab.evals.metrics import average_precision
from retrieval_lab.llm.base import (
    ContextInputs,
    ContextVerdict,
    FaithfulnessInputs,
    FaithfulnessVerdict,
    LLMProvider,
    LLMRequest,
    RelevanceInputs,
    RelevanceVerdict,
    TokenUsage,
)
from retrieval_lab.text import strip_citations

FAITHFULNESS_SYSTEM = """You audit answers produced by a retrieval-augmented system.

Split the answer into its atomic factual claims. For each claim decide whether the context \
passages directly support it. A claim is supported only if a careful reader could verify it \
from the context alone; paraphrase is fine, added facts, changed numbers or reversed meaning \
are not. Ignore citation markers like [1]."""

RELEVANCE_SYSTEM = """You grade whether an answer addresses the question that was asked.

Score from 1 to 5: 5 answers the question directly and completely, 3 is partially on topic, \
1 does not address it. Judge relevance only, not factual accuracy."""

CONTEXT_SYSTEM = """You check which retrieved passages help answer a question.

You get the question, a reference answer with its supporting quote, and numbered passages. For \
each passage, in order, decide whether it contains information that helps arrive at the reference \
answer. Topical overlap alone is not enough. Return exactly one verdict per passage."""

FAITHFULNESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"claim": {"type": "string"}, "supported": {"type": "boolean"}},
                "required": ["claim", "supported"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

CONTEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"useful": {"type": "array", "items": {"type": "boolean"}}},
    "required": ["useful"],
    "additionalProperties": False,
}

RELEVANCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"score": {"type": "integer"}, "reason": {"type": "string"}},
    "required": ["score", "reason"],
    "additionalProperties": False,
}


class FaithfulnessJudgement(BaseModel):
    verdict: FaithfulnessVerdict
    usage: TokenUsage

    @property
    def score(self) -> float | None:
        claims = self.verdict.claims
        if not claims:
            return None
        return sum(c.supported for c in claims) / len(claims)

    @property
    def faithful(self) -> bool:
        return bool(self.verdict.claims) and all(c.supported for c in self.verdict.claims)


class RelevanceJudgement(BaseModel):
    verdict: RelevanceVerdict
    usage: TokenUsage

    @property
    def score(self) -> float:
        return (self.verdict.score - 1) / 4


class ContextJudgement(BaseModel):
    useful: list[bool]
    usage: TokenUsage

    @property
    def precision(self) -> float:
        return average_precision(self.useful)


class Judge:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    async def faithfulness(
        self, question: str, answer: str, contexts: Sequence[str]
    ) -> FaithfulnessJudgement:
        rendered = "\n\n".join(f"<context>\n{c}\n</context>" for c in contexts)
        response = await self._llm.complete(
            LLMRequest(
                system=FAITHFULNESS_SYSTEM,
                prompt=f"{rendered}\n\nQuestion: {question}\n\nAnswer: {strip_citations(answer)}",
                inputs=FaithfulnessInputs(question=question, answer=answer, contexts=list(contexts)),
                max_tokens=4096,
                json_schema=FAITHFULNESS_SCHEMA,
            )
        )
        return FaithfulnessJudgement(verdict=_parse(FaithfulnessVerdict, response.text), usage=response.usage)

    async def context_usefulness(
        self, question: str, reference: str, contexts: Sequence[str]
    ) -> ContextJudgement:
        """RAGAS-style context precision: the judge labels each ranked passage useful or not."""
        rendered = "\n\n".join(f'<passage n="{i}">\n{c}\n</passage>' for i, c in enumerate(contexts, 1))
        response = await self._llm.complete(
            LLMRequest(
                system=CONTEXT_SYSTEM,
                prompt=f"Question: {question}\n\nReference: {reference}\n\n{rendered}",
                inputs=ContextInputs(question=question, reference=reference, contexts=list(contexts)),
                max_tokens=4096,
                json_schema=CONTEXT_SCHEMA,
            )
        )
        verdict = _parse(ContextVerdict, response.text)
        # A short or long verdict list is padded or cut to the passages actually shown.
        useful = (verdict.useful + [False] * len(contexts))[: len(contexts)]
        return ContextJudgement(useful=useful, usage=response.usage)

    async def relevance(self, question: str, answer: str) -> RelevanceJudgement:
        response = await self._llm.complete(
            LLMRequest(
                system=RELEVANCE_SYSTEM,
                prompt=f"Question: {question}\n\nAnswer: {strip_citations(answer)}",
                inputs=RelevanceInputs(question=question, answer=answer),
                max_tokens=2048,
                json_schema=RELEVANCE_SCHEMA,
            )
        )
        return RelevanceJudgement(verdict=_parse(RelevanceVerdict, response.text), usage=response.usage)


def _parse[T: BaseModel](model: type[T], text: str) -> T:
    try:
        return model.model_validate_json(text)
    except ValidationError as exc:
        raise ProviderError(f"Judge returned malformed {model.__name__}: {exc.errors()[0]['msg']}") from exc
