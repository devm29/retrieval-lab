from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from retrieval_lab.generation.citations import Citation
from retrieval_lab.llm.base import ClaimVerdict, TokenUsage

RunMode = Literal["full", "retrieval"]
RunTrigger = Literal["cli", "api", "ci", "seed"]


class ExpectedChunk(BaseModel):
    chunk_id: str
    coverage: float


class RetrievedRecord(BaseModel):
    chunk_id: str
    rank: int
    document_slug: str
    heading: str
    score: float
    evidence_score: float
    coverage: float
    relevant: bool
    useful: bool | None = None
    stage_ranks: dict[str, int] = Field(default_factory=dict)


class QuestionMetrics(BaseModel):
    recall_at_k: float | None = None
    mrr: float | None = None
    ndcg_at_k: float | None = None
    context_precision: float | None = None
    faithfulness: float | None = None
    answer_relevance: float | None = None
    citation_accuracy: float | None = None
    abstained: bool = False
    correct_abstention: bool | None = None


class QuestionResult(BaseModel):
    question_id: str
    question: str
    answerable: bool
    document_slug: str | None
    evidence: str | None
    evidence_found: bool
    expected: list[ExpectedChunk]
    retrieved: list[RetrievedRecord]
    rewritten_query: str | None = None
    metrics: QuestionMetrics
    answer: str | None = None
    abstain_reason: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    claims: list[ClaimVerdict] = Field(default_factory=list)
    relevance_reason: str | None = None
    timings_ms: dict[str, float]
    usage: dict[str, TokenUsage]


class LatencyStats(BaseModel):
    p50: float
    p95: float
    mean: float


class StageCost(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AggregateMetrics(BaseModel):
    recall_at_k: float | None = None
    mrr: float | None = None
    ndcg_at_k: float | None = None
    context_precision: float | None = None
    faithfulness: float | None = None
    answer_relevance: float | None = None
    citation_accuracy: float | None = None
    abstention_accuracy: float | None = None
    false_abstention_rate: float | None = None


class RunEnvironment(BaseModel):
    """Everything besides the pipeline spec that moves scores; two runs are comparable only if it matches."""

    llm_model: str
    judge_model: str
    embedding_model: str
    reranker_model: str
    golden_hash: str


class RunSummary(BaseModel):
    k: int
    mode: RunMode
    environment: RunEnvironment | None = None
    question_count: int
    answerable_count: int
    unanswerable_count: int
    metrics: AggregateMetrics
    latency_ms: dict[str, LatencyStats]
    cost: dict[str, StageCost]
    total_cost_usd: float
    cost_per_query_usd: float


class MetricDelta(BaseModel):
    metric: str
    baseline: float | None
    candidate: float | None
    delta: float | None
    tolerance: float | None
    regressed: bool


class GateTolerance(BaseModel):
    ndcg_at_k: float = Field(default=0.02, ge=0)
    faithfulness: float = Field(default=0.03, ge=0)


class DriftItem(BaseModel):
    field: str
    baseline: str | None
    candidate: str | None
    blocking: bool


class GateResult(BaseModel):
    passed: bool
    config_name: str
    baseline_label: str
    candidate_label: str
    tolerance: GateTolerance
    deltas: list[MetricDelta]
    drift: list[DriftItem] = Field(default_factory=list)

    # Serialised so API clients see that `passed` means nothing when the runs are not comparable.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def comparable(self) -> bool:
        return not any(d.blocking for d in self.drift)


class BaselineFile(BaseModel):
    """A stored baseline, checked into data/baselines so CI can gate without a database history."""

    config_name: str
    spec_hash: str
    created_at: datetime
    llm_model: str
    judge_model: str
    embedding_model: str
    summary: RunSummary


class CalibrationItem(BaseModel):
    id: str
    question: str
    answer: str
    contexts: list[str]
    human_label: Literal["faithful", "unfaithful"]
    note: str | None = None


class CalibrationOutcome(BaseModel):
    id: str
    question: str
    answer: str
    human_label: Literal["faithful", "unfaithful"]
    judge_label: Literal["faithful", "unfaithful"]
    judge_score: float | None
    claims: list[ClaimVerdict]
    agree: bool
    note: str | None = None


class CalibrationReport(BaseModel):
    judge_model: str
    sample_size: int
    kappa: float
    agreement: float
    interpretation: str
    confusion: dict[str, dict[str, int]]
    items: list[CalibrationOutcome]
    usage: TokenUsage
