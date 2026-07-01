"""add key_prefix to api_keys

Revision ID: 005
Revises: 004
Create Date: 2026-05-14

Armazena os primeiros 8 chars da raw_key para identificacao visual.
Keys criadas antes desta migration terao key_prefix = NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("key_prefix", sa.String(8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "key_prefix")
