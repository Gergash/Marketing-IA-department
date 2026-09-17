"""app_users admin flags + api_usage_events — panel de administrador

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("app_users")} if "app_users" in inspector.get_table_names() else set()

    with op.batch_alter_table("app_users") as batch_op:
        if "is_admin" not in cols:
            batch_op.add_column(
                sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        if "is_active" not in cols:
            batch_op.add_column(
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
            )
        if "last_login_at" not in cols:
            batch_op.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))

    tables = set(inspector.get_table_names())
    if "api_usage_events" not in tables:
        op.create_table(
            "api_usage_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("operation", sa.String(length=32), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("credits_cost", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_api_usage_events_tenant_id", "api_usage_events", ["tenant_id"])
        op.create_index("ix_api_usage_events_run_id", "api_usage_events", ["run_id"])
        op.create_index("ix_api_usage_events_provider", "api_usage_events", ["provider"])
        op.create_index("ix_api_usage_events_created_at", "api_usage_events", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "api_usage_events" in tables:
        for idx in (
            "ix_api_usage_events_created_at",
            "ix_api_usage_events_provider",
            "ix_api_usage_events_run_id",
            "ix_api_usage_events_tenant_id",
        ):
            try:
                op.drop_index(idx, table_name="api_usage_events")
            except Exception:
                pass
        op.drop_table("api_usage_events")

    cols = {c["name"] for c in inspector.get_columns("app_users")} if "app_users" in tables else set()
    with op.batch_alter_table("app_users") as batch_op:
        for col in ("last_login_at", "is_active", "is_admin"):
            if col in cols:
                batch_op.drop_column(col)
