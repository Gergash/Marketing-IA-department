"""agent_runs: add run_params_json, revision_notes y revision_count (HITL revise)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persiste los parámetros del run y las notas de revisión para poder regenerar la pieza."""
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("run_params_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("revision_notes", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    """Elimina las columnas de revisión."""
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("revision_count")
        batch_op.drop_column("revision_notes")
        batch_op.drop_column("run_params_json")
