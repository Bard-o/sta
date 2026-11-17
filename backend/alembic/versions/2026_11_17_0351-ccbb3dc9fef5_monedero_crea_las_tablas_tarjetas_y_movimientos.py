"""monedero: crea las tablas tarjetas y movimientos

Revision ID: ccbb3dc9fef5
Revises: afc3be28e833
Create Date: 2026-11-17 03:51:55.455907

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ccbb3dc9fef5"
down_revision: str | None = "afc3be28e833"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "movimientos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "recarga",
                "compra",
                "reembolso",
                name="tipo_movimiento",
                native_enum=False,
                length=9,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("valor", sa.BigInteger(), nullable=False),
        sa.Column("saldo_resultante", sa.BigInteger(), nullable=False),
        sa.Column("referencia", sa.String(length=20), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(tipo = 'compra' AND valor < 0) OR (tipo IN ('recarga', 'reembolso') AND valor > 0)",
            name=op.f("ck_movimientos_valor_con_el_signo_de_su_tipo"),
        ),
        sa.CheckConstraint(
            "saldo_resultante >= 0", name=op.f("ck_movimientos_saldo_resultante_no_negativo")
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["usuarios.id"], name=op.f("fk_movimientos_cliente_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movimientos")),
    )
    op.create_index(
        "ix_movimientos_cliente_creado_en", "movimientos", ["cliente_id", "creado_en"], unique=False
    )
    op.create_index(op.f("ix_movimientos_cliente_id"), "movimientos", ["cliente_id"], unique=False)
    op.create_table(
        "tarjetas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "credito",
                "debito",
                name="tipo_tarjeta",
                native_enum=False,
                length=7,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "franquicia",
            sa.Enum(
                "visa",
                "mastercard",
                "amex",
                "diners",
                "otra",
                name="franquicia_tarjeta",
                native_enum=False,
                length=10,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("titular", sa.String(length=100), nullable=False),
        sa.Column("ultimos_4", sa.String(length=4), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("vencimiento", sa.Date(), nullable=False),
        sa.Column("eliminada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ultimos_4 ~ '^[0-9]{4}$'", name=op.f("ck_tarjetas_ultimos_cuatro_digitos")
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["usuarios.id"], name=op.f("fk_tarjetas_cliente_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tarjetas")),
    )
    op.create_index(
        "ix_tarjetas_cliente_eliminada", "tarjetas", ["cliente_id", "eliminada"], unique=False
    )
    op.create_index(op.f("ix_tarjetas_cliente_id"), "tarjetas", ["cliente_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tarjetas_cliente_id"), table_name="tarjetas")
    op.drop_index("ix_tarjetas_cliente_eliminada", table_name="tarjetas")
    op.drop_table("tarjetas")
    op.drop_index(op.f("ix_movimientos_cliente_id"), table_name="movimientos")
    op.drop_index("ix_movimientos_cliente_creado_en", table_name="movimientos")
    op.drop_table("movimientos")
