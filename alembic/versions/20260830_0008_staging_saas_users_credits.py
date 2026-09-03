"""app_users, credit_wallets, payment_records — staging SaaS + Bold

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index("ix_app_users_email", "app_users", ["email"])
    op.create_index("ix_app_users_tenant_id", "app_users", ["tenant_id"])

    op.create_table(
        "credit_wallets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index("ix_credit_wallets_tenant_id", "credit_wallets", ["tenant_id"])

    op.create_table(
        "payment_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("reference", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="bold"),
        sa.Column("amount_cop", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("payer_email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_payment_records_reference", "payment_records", ["reference"])
    op.create_index("ix_payment_records_tenant_id", "payment_records", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_records_tenant_id", table_name="payment_records")
    op.drop_index("ix_payment_records_reference", table_name="payment_records")
    op.drop_table("payment_records")
    op.drop_index("ix_credit_wallets_tenant_id", table_name="credit_wallets")
    op.drop_table("credit_wallets")
    op.drop_index("ix_app_users_tenant_id", table_name="app_users")
    op.drop_index("ix_app_users_email", table_name="app_users")
    op.drop_table("app_users")
