from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}


class GoldenStatus(enum.StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class GoldenOrigin(enum.StrEnum):
    SEED = "seed"
    SYNTHETIC = "synthetic"
    MANUAL = "manual"


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda members: [m.value for m in members])


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    author: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    chunking: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    # Lexeme occurrences in tsv, i.e. the document length BM25 assumes; filled when stats refresh.
    term_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str] = mapped_column(String(120))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || "
            "setweight(to_tsvector('english', content), 'B')",
            persisted=True,
        ),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class LexemeStat(Base):
    """Document frequencies for BM25 IDF; Postgres FTS has no corpus-level statistics of its own."""

    __tablename__ = "lexeme_stats"

    lexeme: Mapped[str] = mapped_column(Text, primary_key=True)
    ndoc: Mapped[int] = mapped_column(Integer)
    idf: Mapped[float] = mapped_column(Float)


class CorpusStats(Base):
    """Single row of collection-level BM25 statistics, refreshed after every ingest."""

    __tablename__ = "corpus_stats"
    __table_args__ = (CheckConstraint("id = 1", name="corpus_stats_single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    chunk_count: Mapped[int] = mapped_column(Integer)
    avg_term_count: Mapped[float] = mapped_column(Float)


class PipelineConfigRow(Base):
    __tablename__ = "pipeline_configs"
    __table_args__ = (UniqueConstraint("name", "version"), UniqueConstraint("name", "spec_hash"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    spec_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default="")
    spec: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GoldenQuestion(Base):
    __tablename__ = "golden_questions"
    __table_args__ = (Index("ix_golden_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    question: Mapped[str] = mapped_column(Text)
    document_slug: Mapped[str | None] = mapped_column(String(120))
    evidence: Mapped[str | None] = mapped_column(Text)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    answerable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[GoldenStatus] = mapped_column(_enum(GoldenStatus, "golden_status"))
    origin: Mapped[GoldenOrigin] = mapped_column(_enum(GoldenOrigin, "golden_origin"))
    source_chunk_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (Index("ix_eval_runs_config_created", "config_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_configs.id"))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"))
    mode: Mapped[str] = mapped_column(String(20))
    trigger: Mapped[str] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(200))
    k: Mapped[int] = mapped_column(Integer)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    llm_model: Mapped[str] = mapped_column(String(120))
    judge_model: Mapped[str] = mapped_column(String(120))
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    config: Mapped[PipelineConfigRow] = relationship(lazy="joined")


class EvalResult(Base):
    __tablename__ = "eval_results"
    __table_args__ = (
        UniqueConstraint("run_id", "question_id"),
        Index("ix_eval_results_question", "question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("golden_questions.id", ondelete="CASCADE"))
    ndcg: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    question: Mapped[GoldenQuestion] = relationship(lazy="joined")


class Baseline(Base):
    __tablename__ = "baselines"

    config_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"))
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JudgeCalibration(Base):
    __tablename__ = "judge_calibrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    judge_model: Mapped[str] = mapped_column(String(120))
    sample_size: Mapped[int] = mapped_column(Integer)
    kappa: Mapped[float] = mapped_column(Float)
    agreement: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
