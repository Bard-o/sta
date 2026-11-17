"""reservas: agrega transacciones, tramos, viajeros y tiquetes

Revision ID: afc3be28e833
Revises: 6e79896ed4f7
Create Date: 2026-11-17 00:27:21.335745

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "afc3be28e833"
down_revision: str | None = "6e79896ed4f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transacciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "reserva",
                "compra",
                name="tipo_transaccion",
                native_enum=False,
                length=7,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente",
                "vigente",
                "pagada",
                "vencida",
                "activa",
                "cancelada",
                "realizada",
                "reembolsada",
                "reubicada",
                name="estado_transaccion",
                native_enum=False,
                length=11,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("codigo", sa.String(length=6), nullable=True),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bloqueo_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tipo <> 'reserva' OR vence_en IS NOT NULL",
            name=op.f("ck_transacciones_reserva_con_vencimiento"),
        ),
        sa.CheckConstraint(
            "codigo IS NULL OR length(codigo) = 6",
            name=op.f("ck_transacciones_codigo_de_seis_caracteres"),
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["usuarios.id"], name=op.f("fk_transacciones_cliente_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transacciones")),
        sa.UniqueConstraint("codigo", name=op.f("uq_transacciones_codigo")),
    )
    op.create_index(
        "ix_transacciones_cliente_estado", "transacciones", ["cliente_id", "estado"], unique=False
    )
    op.create_index(
        op.f("ix_transacciones_cliente_id"), "transacciones", ["cliente_id"], unique=False
    )

    op.create_table(
        "tramos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaccion_id", sa.Integer(), nullable=False),
        sa.Column("vuelo_id", sa.Integer(), nullable=False),
        sa.Column(
            "clase",
            sa.Enum(
                "economica",
                "primera",
                name="clase_tramo",
                native_enum=False,
                length=9,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("precio", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.CheckConstraint("orden BETWEEN 1 AND 2", name=op.f("ck_tramos_orden_valido")),
        sa.CheckConstraint("precio > 0", name=op.f("ck_tramos_precio_positivo")),
        sa.ForeignKeyConstraint(
            ["transaccion_id"],
            ["transacciones.id"],
            name=op.f("fk_tramos_transaccion_id_transacciones"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vuelo_id"], ["vuelos.id"], name=op.f("fk_tramos_vuelo_id_vuelos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tramos")),
        sa.UniqueConstraint(
            "transaccion_id", "orden", "clase", name="uq_tramos_transaccion_orden_clase"
        ),
    )
    op.create_index(op.f("ix_tramos_transaccion_id"), "tramos", ["transaccion_id"], unique=False)
    op.create_index(op.f("ix_tramos_vuelo_id"), "tramos", ["vuelo_id"], unique=False)

    op.create_table(
        "viajeros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaccion_id", sa.Integer(), nullable=False),
        sa.Column("tipo_documento", sa.String(length=2), nullable=False),
        sa.Column("numero_documento", sa.String(length=20), nullable=False),
        sa.Column("nombres", sa.String(length=100), nullable=False),
        sa.Column("apellidos", sa.String(length=100), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=False),
        sa.Column(
            "genero",
            sa.Enum(
                "femenino",
                "masculino",
                "otro",
                name="genero_viajero",
                native_enum=False,
                length=9,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("telefono", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("contacto_nombre", sa.String(length=100), nullable=False),
        sa.Column("contacto_telefono", sa.String(length=20), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["transaccion_id"],
            ["transacciones.id"],
            name=op.f("fk_viajeros_transaccion_id_transacciones"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_viajeros")),
        sa.UniqueConstraint(
            "transaccion_id",
            "tipo_documento",
            "numero_documento",
            name="uq_viajeros_transaccion_documento",
        ),
    )
    op.create_index(
        op.f("ix_viajeros_transaccion_id"), "viajeros", ["transaccion_id"], unique=False
    )

    op.create_table(
        "tiquetes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tramo_id", sa.Integer(), nullable=False),
        sa.Column("viajero_id", sa.Integer(), nullable=False),
        sa.Column("vuelo_id", sa.Integer(), nullable=False),
        sa.Column("numero_silla", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "bloqueado",
                "reservado",
                "comprado",
                "cancelado",
                "vencido",
                "reembolsado",
                "reubicado",
                name="estado_tiquete",
                native_enum=False,
                length=11,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("tipo_documento", sa.String(length=2), nullable=False),
        sa.Column("numero_documento", sa.String(length=20), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("numero_silla > 0", name=op.f("ck_tiquetes_silla_positiva")),
        sa.ForeignKeyConstraint(
            ["tramo_id"],
            ["tramos.id"],
            name=op.f("fk_tiquetes_tramo_id_tramos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["viajero_id"],
            ["viajeros.id"],
            name=op.f("fk_tiquetes_viajero_id_viajeros"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vuelo_id"], ["vuelos.id"], name=op.f("fk_tiquetes_vuelo_id_vuelos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tiquetes")),
        sa.UniqueConstraint("tramo_id", "viajero_id", name="uq_tiquetes_tramo_viajero"),
    )
    op.create_index(op.f("ix_tiquetes_tramo_id"), "tiquetes", ["tramo_id"], unique=False)
    op.create_index(op.f("ix_tiquetes_viajero_id"), "tiquetes", ["viajero_id"], unique=False)
    op.create_index("ix_tiquetes_vuelo_estado", "tiquetes", ["vuelo_id", "estado"], unique=False)
    op.create_index(op.f("ix_tiquetes_vuelo_id"), "tiquetes", ["vuelo_id"], unique=False)
    op.create_index(
        "uq_tiquetes_vuelo_documento_activo",
        "tiquetes",
        ["vuelo_id", "tipo_documento", "numero_documento"],
        unique=True,
        postgresql_where=sa.text("estado IN ('bloqueado', 'reservado', 'comprado')"),
    )
    op.create_index(
        "uq_tiquetes_vuelo_silla_activa",
        "tiquetes",
        ["vuelo_id", "numero_silla"],
        unique=True,
        postgresql_where=sa.text("estado IN ('bloqueado', 'reservado', 'comprado')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_tiquetes_vuelo_silla_activa",
        table_name="tiquetes",
        postgresql_where=sa.text("estado IN ('bloqueado', 'reservado', 'comprado')"),
    )
    op.drop_index(
        "uq_tiquetes_vuelo_documento_activo",
        table_name="tiquetes",
        postgresql_where=sa.text("estado IN ('bloqueado', 'reservado', 'comprado')"),
    )
    op.drop_index(op.f("ix_tiquetes_vuelo_id"), table_name="tiquetes")
    op.drop_index("ix_tiquetes_vuelo_estado", table_name="tiquetes")
    op.drop_index(op.f("ix_tiquetes_viajero_id"), table_name="tiquetes")
    op.drop_index(op.f("ix_tiquetes_tramo_id"), table_name="tiquetes")
    op.drop_table("tiquetes")
    op.drop_index(op.f("ix_viajeros_transaccion_id"), table_name="viajeros")
    op.drop_table("viajeros")
    op.drop_index(op.f("ix_tramos_vuelo_id"), table_name="tramos")
    op.drop_index(op.f("ix_tramos_transaccion_id"), table_name="tramos")
    op.drop_table("tramos")
    op.drop_index(op.f("ix_transacciones_cliente_id"), table_name="transacciones")
    op.drop_index("ix_transacciones_cliente_estado", table_name="transacciones")
    op.drop_table("transacciones")
