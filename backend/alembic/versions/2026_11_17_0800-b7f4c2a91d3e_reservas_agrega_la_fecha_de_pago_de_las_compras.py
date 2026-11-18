"""reservas: agrega la fecha de pago de las compras

Revision ID: b7f4c2a91d3e
Revises: 3f7a9c1b2d4e
Create Date: 2026-11-17 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7f4c2a91d3e"
down_revision: str | None = "3f7a9c1b2d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transacciones",
        sa.Column("pagada_en", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transacciones", "pagada_en")
