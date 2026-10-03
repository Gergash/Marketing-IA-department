"""Bandeja de DMs: dm_contacts, dm_messages y oauth_tokens.dm_agent_enabled

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "oauth_tokens" in tables:
        cols = {c["name"] for c in inspector.get_columns("oauth_tokens")}
        if "dm_agent_enabled" not in cols:
            op.add_column(
                "oauth_tokens",
                sa.Column("dm_agent_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    if "dm_contacts" not in tables:
        op.create_table(
            "dm_contacts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("oauth_token_id", sa.Integer(), nullable=True),
            sa.Column("platform", sa.String(16), nullable=False),
            sa.Column("sender_id", sa.String(64), nullable=False),
            sa.Column("display_name", sa.String(256), nullable=True),
            sa.Column("full_name", sa.String(256), nullable=True),
            sa.Column("phone", sa.String(64), nullable=True),
            sa.Column("city", sa.String(128), nullable=True),
            sa.Column("motive", sa.Text(), nullable=True),
            sa.Column("motive_category", sa.String(32), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="nuevo"),
            sa.Column("bot_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("privacy_notice_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_message_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                "tenant_id", "platform", "sender_id", name="uq_dm_contact_tenant_platform_sender"
            ),
        )
        op.create_index("ix_dm_contacts_id", "dm_contacts", ["id"])
        op.create_index("ix_dm_contacts_tenant_id", "dm_contacts", ["tenant_id"])
        op.create_index("ix_dm_contacts_oauth_token_id", "dm_contacts", ["oauth_token_id"])
        op.create_index("ix_dm_contacts_motive_category", "dm_contacts", ["motive_category"])
        op.create_index("ix_dm_contacts_status", "dm_contacts", ["status"])
        op.create_index("ix_dm_contacts_last_message_at", "dm_contacts", ["last_message_at"])

    if "dm_messages" not in tables:
        op.create_table(
            "dm_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contact_id", sa.Integer(), nullable=False),
            sa.Column("direction", sa.String(8), nullable=False),
            sa.Column("sent_by", sa.String(16), nullable=False),
            sa.Column("text", sa.Text(), nullable=False, server_default=""),
            sa.Column("meta_mid", sa.String(255), nullable=True, unique=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_dm_messages_id", "dm_messages", ["id"])
        op.create_index("ix_dm_messages_contact_id", "dm_messages", ["contact_id"])
        op.create_index("ix_dm_messages_created_at", "dm_messages", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "dm_messages" in tables:
        op.drop_table("dm_messages")
    if "dm_contacts" in tables:
        op.drop_table("dm_contacts")
    if "oauth_tokens" in tables:
        cols = {c["name"] for c in inspector.get_columns("oauth_tokens")}
        if "dm_agent_enabled" in cols:
            op.drop_column("oauth_tokens", "dm_agent_enabled")
