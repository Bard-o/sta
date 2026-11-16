"""usuarios: agrega el lugar de nacimiento por pais, departamento y municipio

Revision ID: 2c29e5d7ce76
Revises: 7c1d9b3e5a24
Create Date: 2026-11-09 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2c29e5d7ce76"
down_revision: str | None = "7c1d9b3e5a24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # HU-01: el lugar de nacimiento deja de ser texto libre. Las cuentas anteriores quedan en
    # null y conservan su texto en `lugar_nacimiento`; al editar el perfil se les pide completarlo.
    # El texto ahora puede ser «ciudad, país»: una ciudad de 120 caracteres más un país largo.
    op.alter_column(
        "usuarios",
        "lugar_nacimiento",
        existing_type=sa.String(length=120),
        type_=sa.String(length=200),
        existing_nullable=True,
    )
    op.add_column("usuarios", sa.Column("pais_nacimiento", sa.String(length=2), nullable=True))
    op.add_column("usuarios", sa.Column("municipio_nacimiento", sa.String(length=5), nullable=True))
    op.add_column("usuarios", sa.Column("ciudad_nacimiento", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("usuarios", "ciudad_nacimiento")
    op.drop_column("usuarios", "municipio_nacimiento")
    op.drop_column("usuarios", "pais_nacimiento")
    op.alter_column(
        "usuarios",
        "lugar_nacimiento",
        existing_type=sa.String(length=200),
        type_=sa.String(length=120),
        existing_nullable=True,
    )
