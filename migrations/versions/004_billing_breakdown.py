"""add api_key_id + llm_provider to billing_records, owner to api_keys

Revision ID: 004
Revises: 003
Create Date: 2026-05-13

Registros historicos terao api_key_id = NULL e llm_provider = NULL.
O Power BI deve agrupar NULL como "(sem dados)".
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billing_records",
        sa.Column("api_key_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "billing_records",
        sa.Column("llm_provider", sa.String(50), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_records_api_key_id",
        "billing_records",
        "api_keys",
        ["api_key_id"],
        ["id"],
    )
    op.create_index(
        "ix_billing_records_api_key_id_created_at",
        "billing_records",
        ["api_key_id", "created_at"],
    )
    op.create_index(
        "ix_billing_records_llm_provider_created_at",
        "billing_records",
        ["llm_provider", "created_at"],
    )

    op.add_column(
        "api_keys",
        sa.Column("owner", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "owner")

    op.drop_index("ix_billing_records_llm_provider_created_at", table_name="billing_records")
    op.drop_index("ix_billing_records_api_key_id_created_at", table_name="billing_records")
    op.drop_constraint("fk_billing_records_api_key_id", "billing_records", type_="foreignkey")
    op.drop_column("billing_records", "llm_provider")
    op.drop_column("billing_records", "api_key_id")
