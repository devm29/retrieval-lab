"""bm25 document length, corpus stats and an eval_results question index

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("term_count", sa.Integer(), nullable=True))
    op.create_table(
        "corpus_stats",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("avg_term_count", sa.Float(), nullable=False),
        sa.CheckConstraint("id = 1", name="corpus_stats_single_row"),
    )
    op.create_index("ix_eval_results_question", "eval_results", ["question_id"])
    op.execute(
        "UPDATE chunks SET term_count = (SELECT coalesce(sum(cardinality(positions)), 0) FROM unnest(tsv))"
    )
    op.execute(
        "INSERT INTO corpus_stats (id, chunk_count, avg_term_count) "
        "SELECT 1, count(*), coalesce(avg(term_count), 0) FROM chunks"
    )


def downgrade() -> None:
    op.drop_index("ix_eval_results_question", table_name="eval_results")
    op.drop_table("corpus_stats")
    op.drop_column("chunks", "term_count")
