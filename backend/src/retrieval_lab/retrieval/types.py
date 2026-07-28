from __future__ import annotations

from pydantic import BaseModel, Field

from retrieval_lab.llm.base import TokenUsage


class RetrievedChunk(BaseModel):
    chunk_id: str
    rank: int
    document_slug: str
    document_title: str
    heading: str
    content: str
    char_start: int
    char_end: int
    score: float = Field(description="Score from the final ranking stage.")
    evidence_score: float = Field(description="Calibrated [0, 1] confidence used for abstention.")
    stage_scores: dict[str, float] = Field(default_factory=dict)
    stage_ranks: dict[str, int] = Field(default_factory=dict)


class RetrievalOutcome(BaseModel):
    query: str
    rewritten_query: str | None = None
    chunks: list[RetrievedChunk]
    timings_ms: dict[str, float]
    usage: dict[str, TokenUsage] = Field(default_factory=dict)
