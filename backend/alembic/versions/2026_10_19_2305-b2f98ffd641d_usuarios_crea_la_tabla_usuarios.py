"""usuarios: crea la tabla usuarios

Revision ID: b2f98ffd641d
Revises:
Create Date: 2026-10-19 23:05:22.994543

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2f98ffd641d"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre_usuario", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "rol",
            sa.Enum(
                "root",
                "admin",
                "cliente",
                name="rol",
                native_enum=False,
                length=10,
            ),
            nullable=False,
        ),
        sa.Column(
            "email_verificado", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version_sesion", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rol IN ('root', 'admin', 'cliente')", name=op.f("ck_usuarios_rol")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
        sa.UniqueConstraint("nombre_usuario", name=op.f("uq_usuarios_nombre_usuario")),
        sa.UniqueConstraint("rol", "email", name="uq_usuarios_rol_email"),
    )


def downgrade() -> None:
    op.drop_table("usuarios")
