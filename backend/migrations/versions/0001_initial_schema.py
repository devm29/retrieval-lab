"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSV_EXPRESSION = (
    "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || "
    "setweight(to_tsvector('english', content), 'B')"
)


def _timestamps(*names: str, nullable: bool = False) -> list[sa.Column[datetime]]:
    return [sa.Column(name, sa.DateTime(timezone=True), nullable=nullable) for name in names]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("author", sa.String(300)),
        sa.Column("source_url", sa.String(500)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("chunking", postgresql.JSONB(), nullable=False),
        *_timestamps("created_at", "updated_at"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column(
            "document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(TSV_EXPRESSION, persisted=True), nullable=False),
        sa.UniqueConstraint("document_id", "ordinal"),
    )
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "pipeline_configs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        *_timestamps("created_at"),
        sa.UniqueConstraint("name", "version"),
        sa.UniqueConstraint("name", "spec_hash"),
    )

    op.create_table(
        "golden_questions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("external_id", sa.String(80), unique=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("document_slug", sa.String(120)),
        sa.Column("evidence", sa.Text()),
        sa.Column("reference_answer", sa.Text()),
        sa.Column("answerable", sa.Boolean(), nullable=False),
        sa.Column(
            "status", sa.Enum("proposed", "accepted", "rejected", name="golden_status"), nullable=False
        ),
        sa.Column("origin", sa.Enum("seed", "synthetic", "manual", name="golden_origin"), nullable=False),
        sa.Column("source_chunk_id", sa.String(160)),
        *_timestamps("created_at"),
        *_timestamps("reviewed_at", nullable=True),
    )
    op.create_index("ix_golden_status", "golden_questions", ["status"])

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("config_id", sa.UUID(), sa.ForeignKey("pipeline_configs.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "completed", "failed", name="run_status"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("k", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("llm_model", sa.String(120), nullable=False),
        sa.Column("judge_model", sa.String(120), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text()),
        *_timestamps("created_at"),
        *_timestamps("started_at", "finished_at", nullable=True),
    )
    op.create_index("ix_eval_runs_config_created", "eval_runs", ["config_id", "created_at"])

    op.create_table(
        "eval_results",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "question_id",
            sa.UUID(),
            sa.ForeignKey("golden_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ndcg", sa.Float()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        *_timestamps("created_at"),
        sa.UniqueConstraint("run_id", "question_id"),
    )

    op.create_table(
        "baselines",
        sa.Column("config_name", sa.String(120), primary_key=True),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False),
        *_timestamps("promoted_at"),
    )

    op.create_table(
        "judge_calibrations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("judge_model", sa.String(120), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("kappa", sa.Float(), nullable=False),
        sa.Column("agreement", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        *_timestamps("created_at"),
    )


def downgrade() -> None:
    for table in (
        "judge_calibrations",
        "baselines",
        "eval_results",
        "eval_runs",
        "golden_questions",
        "pipeline_configs",
        "chunks",
        "documents",
    ):
        op.drop_table(table)
    for enum_name in ("run_status", "golden_origin", "golden_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
