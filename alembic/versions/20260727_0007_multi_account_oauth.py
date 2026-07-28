"""oauth_tokens multi-cuenta + agent_runs.social_account_id

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Permite N cuentas por (tenant, provider) y vincula cada run a una cuenta destino."""
    with op.batch_alter_table("oauth_tokens") as batch_op:
        batch_op.add_column(sa.Column("account_name", sa.String(256), nullable=True))
        batch_op.add_column(sa.Column("profile_picture_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("page_id", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true")
        )
        batch_op.create_unique_constraint(
            "uq_oauth_tenant_provider_account", ["tenant_id", "provider", "account_id"]
        )

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("social_account_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_agent_runs_social_account_id", ["social_account_id"])


def downgrade() -> None:
    """Revierte multi-cuenta (las filas extra por proveedor quedarían duplicadas)."""
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_index("ix_agent_runs_social_account_id")
        batch_op.drop_column("social_account_id")

    with op.batch_alter_table("oauth_tokens") as batch_op:
        batch_op.drop_constraint("uq_oauth_tenant_provider_account", type_="unique")
        batch_op.drop_column("is_active")
        batch_op.drop_column("page_id")
        batch_op.drop_column("profile_picture_url")
        batch_op.drop_column("account_name")
