from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from retrieval_lab.db.models import GoldenOrigin, GoldenStatus, RunStatus
from retrieval_lab.evals.schemas import (
    AggregateMetrics,
    CalibrationReport,
    GateResult,
    QuestionMetrics,
    QuestionResult,
    RunMode,
    RunSummary,
)
from retrieval_lab.generation.service import QueryResult
from retrieval_lab.retrieval.config import SLUG_PATTERN, PipelineSpec


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    offline: bool
    llm_model: str
    judge_model: str
    embedding_model: str
    reranker_model: str
    chunk_count: int


class DocumentOut(BaseModel):
    slug: str
    title: str
    author: str | None
    source_url: str | None
    characters: int
    chunk_count: int


class CorpusOut(BaseModel):
    documents: list[DocumentOut]
    chunk_count: int
    embedding_model: str


class ChunkOut(BaseModel):
    id: str
    document_slug: str
    document_title: str
    heading: str
    content: str
    char_start: int
    char_end: int
    token_count: int


class ConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: int
    kind: str
    spec_hash: str
    description: str
    spec: dict[str, Any]
    created_at: datetime
    is_latest: bool = False


class ConfigCreate(BaseModel):
    name: str = Field(pattern=SLUG_PATTERN)
    description: str = Field(default="", max_length=500)
    spec: PipelineSpec


class ConfigCreated(BaseModel):
    config: ConfigOut
    created: bool


class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    config: str = Field(default="hybrid-rerank", max_length=200)


class QueryOut(BaseModel):
    config: ConfigOut
    result: QueryResult
    total_cost_usd: float


class GoldenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str | None
    question: str
    document_slug: str | None
    evidence: str | None
    reference_answer: str | None
    answerable: bool
    status: GoldenStatus
    origin: GoldenOrigin
    source_chunk_id: str | None
    created_at: datetime
    reviewed_at: datetime | None


class GoldenPage(Page[GoldenOut]):
    counts: dict[str, int]


class GoldenCreate(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    answerable: bool = True
    document_slug: str | None = Field(default=None, max_length=120)
    evidence: str | None = Field(default=None, max_length=4000)
    reference_answer: str | None = Field(default=None, max_length=2000)


class GoldenUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=5, max_length=1000)
    document_slug: str | None = Field(default=None, max_length=120)
    evidence: str | None = Field(default=None, max_length=4000)
    reference_answer: str | None = Field(default=None, max_length=2000)
    answerable: bool | None = None
    status: GoldenStatus | None = None

    @field_validator("question", "answerable", "status")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Omitting these fields leaves them unchanged; an explicit null would clear a NOT NULL column.
        if value is None:
            raise ValueError("may be omitted but not set to null")
        return value


class SynthesizeIn(BaseModel):
    count: int = Field(default=5, ge=1, le=50)
    document_slug: str | None = None


class SynthesizeOut(BaseModel):
    created: int
    skipped: int
    cost_usd: float
    questions: list[GoldenOut]


class RunCreate(BaseModel):
    config: str = Field(max_length=200)
    mode: RunMode = "full"
    k: int | None = Field(default=None, ge=1, le=50)
    label: str | None = Field(default=None, max_length=200)


class RunOut(BaseModel):
    id: uuid.UUID
    config: ConfigOut
    status: RunStatus
    mode: str
    trigger: str
    label: str | None
    k: int
    question_count: int
    completed_count: int
    llm_model: str
    judge_model: str
    summary: RunSummary | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    is_baseline: bool = False


class ResultRow(BaseModel):
    question_id: uuid.UUID
    external_id: str | None
    question: str
    answerable: bool
    document_slug: str | None
    metrics: QuestionMetrics
    abstain_reason: str | None
    total_ms: float | None


class RetrievedChunkOut(BaseModel):
    chunk_id: str
    rank: int
    document_slug: str
    document_title: str
    heading: str
    content: str | None
    score: float
    evidence_score: float
    coverage: float
    relevant: bool
    stage_ranks: dict[str, int]
    highlight: tuple[int, int] | None = Field(
        default=None, description="Evidence span relative to the chunk content, when they overlap."
    )


class ExpectedChunkOut(BaseModel):
    chunk_id: str
    coverage: float
    retrieved_rank: int | None
    heading: str | None
    content: str | None
    highlight: tuple[int, int] | None = None


class ResultDetail(BaseModel):
    run_id: uuid.UUID
    config_name: str
    k: int
    max_context_chunks: int
    rewrite_applies_to: Literal["bm25", "dense", "both"] | None
    result: QuestionResult
    retrieved: list[RetrievedChunkOut]
    expected: list[ExpectedChunkOut]


class LeaderboardRow(BaseModel):
    config: ConfigOut
    run_id: uuid.UUID
    finished_at: datetime | None
    metrics: AggregateMetrics
    p50_ms: float | None
    p95_ms: float | None
    cost_per_query_usd: float
    gate: GateResult | None
    is_baseline: bool


class HistoryPoint(BaseModel):
    run_id: uuid.UUID
    version: int
    finished_at: datetime | None
    label: str | None
    metrics: AggregateMetrics


class BaselineIn(BaseModel):
    run_id: uuid.UUID


class QuestionDelta(BaseModel):
    question_id: uuid.UUID
    question: str
    baseline_ndcg: float | None
    candidate_ndcg: float | None
    delta: float | None


class CompareOut(BaseModel):
    baseline: RunOut
    candidate: RunOut
    gate: GateResult
    questions: list[QuestionDelta]


class CalibrationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    report: CalibrationReport
