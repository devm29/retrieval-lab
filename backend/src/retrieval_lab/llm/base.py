from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, Field

ABSTAIN_TOKEN = "INSUFFICIENT_EVIDENCE"


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


class SourcePassage(BaseModel):
    marker: int
    chunk_id: str
    title: str
    text: str


class AnswerInputs(BaseModel):
    task: Literal["answer"] = "answer"
    question: str
    sources: list[SourcePassage]


class RewriteInputs(BaseModel):
    task: Literal["rewrite"] = "rewrite"
    question: str


class FaithfulnessInputs(BaseModel):
    task: Literal["judge_faithfulness"] = "judge_faithfulness"
    question: str
    answer: str
    contexts: list[str]


class RelevanceInputs(BaseModel):
    task: Literal["judge_relevance"] = "judge_relevance"
    question: str
    answer: str


class ContextInputs(BaseModel):
    task: Literal["judge_context"] = "judge_context"
    question: str
    reference: str
    contexts: list[str]


class SynthesisInputs(BaseModel):
    task: Literal["synthesize_question"] = "synthesize_question"
    title: str
    heading: str
    passage: str


class ClaimVerdict(BaseModel):
    claim: str
    supported: bool


class FaithfulnessVerdict(BaseModel):
    claims: list[ClaimVerdict]


class RelevanceVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str


class ContextVerdict(BaseModel):
    useful: list[bool]


class SynthesizedQuestion(BaseModel):
    question: str
    evidence: str
    answer: str


TaskInputs = Annotated[
    AnswerInputs | RewriteInputs | FaithfulnessInputs | RelevanceInputs | ContextInputs | SynthesisInputs,
    Field(discriminator="task"),
]


class LLMRequest(BaseModel):
    """A rendered prompt plus the structured inputs it was rendered from.

    Hosted providers only read `system`/`prompt`; deterministic providers work
    from `inputs`, which keeps them independent of prompt wording.
    """

    system: str
    prompt: str
    inputs: TaskInputs
    max_tokens: int = 1024
    json_schema: dict[str, Any] | None = None


class LLMResponse(BaseModel):
    text: str
    model: str
    usage: TokenUsage
    latency_ms: float


class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
