"""app_users.auth0_sub — identidad Auth0 (RS256 ID token)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "app_users" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("app_users")}
    if "auth0_sub" not in cols:
        op.add_column("app_users", sa.Column("auth0_sub", sa.String(length=128), nullable=True))
    # Índice único (nullable: varios NULL permitidos en Postgres)
    indexes = {ix["name"] for ix in inspector.get_indexes("app_users")}
    if "ix_app_users_auth0_sub" not in indexes:
        op.create_index("ix_app_users_auth0_sub", "app_users", ["auth0_sub"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "app_users" not in tables:
        return
    indexes = {ix["name"] for ix in inspector.get_indexes("app_users")}
    if "ix_app_users_auth0_sub" in indexes:
        op.drop_index("ix_app_users_auth0_sub", table_name="app_users")
    cols = {c["name"] for c in inspector.get_columns("app_users")}
    if "auth0_sub" in cols:
        op.drop_column("app_users", "auth0_sub")
