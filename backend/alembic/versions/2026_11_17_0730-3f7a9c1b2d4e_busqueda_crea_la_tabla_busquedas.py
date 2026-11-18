"""busqueda: crea la tabla busquedas

Revision ID: 3f7a9c1b2d4e
Revises: e39140d3a16f
Create Date: 2026-11-17 07:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3f7a9c1b2d4e"
down_revision: str | None = "e39140d3a16f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "busquedas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("criterios", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column(
            "registrada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_busquedas_usuario_id_usuarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_busquedas")),
    )
    op.create_index(op.f("ix_busquedas_usuario_id"), "busquedas", ["usuario_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_busquedas_usuario_id"), table_name="busquedas")
    op.drop_table("busquedas")
