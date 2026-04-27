"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-04-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "briefs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("tema", sa.String(length=255), nullable=False),
        sa.Column("publico_objetivo", sa.String(length=255), nullable=False),
        sa.Column("red_social", sa.String(length=80), nullable=False),
        sa.Column("objetivo", sa.String(length=80), nullable=False),
        sa.Column("tono_marca", sa.String(length=120), nullable=False),
        sa.Column("idioma", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_briefs_id", "briefs", ["id"])
    op.create_index("ix_briefs_tenant_id", "briefs", ["tenant_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("brief_id", sa.Integer(), nullable=False),
        sa.Column("run_mode", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_id", "agent_runs", ["id"])
    op.create_index("ix_agent_runs_tenant_id", "agent_runs", ["tenant_id"])
    op.create_index("ix_agent_runs_brief_id", "agent_runs", ["brief_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_idempotency_key", "agent_runs", ["idempotency_key"])

    op.create_table(
        "generated_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("image_prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_assets_id", "generated_assets", ["id"])
    op.create_index("ix_generated_assets_tenant_id", "generated_assets", ["tenant_id"])
    op.create_index("ix_generated_assets_run_id", "generated_assets", ["run_id"])

    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("publication_url", sa.Text(), nullable=False),
        sa.Column("platform_post_id", sa.String(length=128), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_publications_id", "publications", ["id"])
    op.create_index("ix_publications_tenant_id", "publications", ["tenant_id"])
    op.create_index("ix_publications_run_id", "publications", ["run_id"])
    op.create_index("ix_publications_platform_post_id", "publications", ["platform_post_id"])

    op.create_table(
        "campaign_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("tema", sa.String(length=255), nullable=False),
        sa.Column("red_social", sa.String(length=80), nullable=False),
        sa.Column("objetivo", sa.String(length=80), nullable=False),
        sa.Column("cron_expr", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_schedules_id", "campaign_schedules", ["id"])
    op.create_index("ix_campaign_schedules_tenant_id", "campaign_schedules", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("campaign_schedules")
    op.drop_table("publications")
    op.drop_table("generated_assets")
    op.drop_table("agent_runs")
    op.drop_table("briefs")
