"""bm25 lexeme statistics

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lexeme_stats",
        sa.Column("lexeme", sa.Text(), primary_key=True),
        sa.Column("ndoc", sa.Integer(), nullable=False),
        sa.Column("idf", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lexeme_stats")
