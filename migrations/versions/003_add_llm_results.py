"""add llm_results jsonb column to validation_requests

Revision ID: 003
Revises: 002
Create Date: 2026-05-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "validation_requests",
        sa.Column("llm_results", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("validation_requests", "llm_results")
