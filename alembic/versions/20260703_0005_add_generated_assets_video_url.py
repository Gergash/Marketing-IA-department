"""generated_assets: add nullable video_url (Reels)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade video_url (nullable) para persistir el render de Reels sin afectar filas de imagen existentes."""
    with op.batch_alter_table("generated_assets") as batch_op:
        batch_op.add_column(sa.Column("video_url", sa.Text(), nullable=True))


def downgrade() -> None:
    """Elimina la columna video_url."""
    with op.batch_alter_table("generated_assets") as batch_op:
        batch_op.drop_column("video_url")
