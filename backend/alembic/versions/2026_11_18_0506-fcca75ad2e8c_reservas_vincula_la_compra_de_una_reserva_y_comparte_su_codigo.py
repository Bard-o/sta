"""reservas: vincula la compra de una reserva y comparte su codigo

Revision ID: fcca75ad2e8c
Revises: 2f61c813b097
Create Date: 2026-11-18 05:06:58.121033

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fcca75ad2e8c"
down_revision: str | None = "2f61c813b097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transacciones", sa.Column("reserva_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_transacciones_reserva_id_transacciones"),
        "transacciones",
        "transacciones",
        ["reserva_id"],
        ["id"],
    )
    op.create_unique_constraint(
        op.f("uq_transacciones_reserva_id"), "transacciones", ["reserva_id"]
    )
    # Autogenerate no detecta los CHECK: solo una compra puede venir de pagar una reserva.
    op.create_check_constraint(
        op.f("ck_transacciones_compra_de_reserva"),
        "transacciones",
        "reserva_id IS NULL OR tipo = 'compra'",
    )
    # HU-27: la compra de una reserva repite su código; los demás siguen siendo únicos (RF-39).
    op.drop_constraint(op.f("uq_transacciones_codigo"), "transacciones", type_="unique")
    op.create_index(
        "uq_transacciones_codigo_sin_reserva",
        "transacciones",
        ["codigo"],
        unique=True,
        postgresql_where=sa.text("reserva_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_transacciones_codigo_sin_reserva",
        table_name="transacciones",
        postgresql_where=sa.text("reserva_id IS NULL"),
    )
    # La restricción anterior no admite el código repetido: la compra de una reserva lo pierde.
    op.execute("UPDATE transacciones SET codigo = NULL WHERE reserva_id IS NOT NULL")
    op.create_unique_constraint(op.f("uq_transacciones_codigo"), "transacciones", ["codigo"])
    op.drop_constraint(op.f("ck_transacciones_compra_de_reserva"), "transacciones", type_="check")
    op.drop_constraint(op.f("uq_transacciones_reserva_id"), "transacciones", type_="unique")
    op.drop_constraint(
        op.f("fk_transacciones_reserva_id_transacciones"), "transacciones", type_="foreignkey"
    )
    op.drop_column("transacciones", "reserva_id")
