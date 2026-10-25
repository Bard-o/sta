"""vuelos: agrega las coordenadas de las ciudades

Revision ID: 7c1d9b3e5a24
Revises: e0173070e9cb
Create Date: 2026-10-25 18:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c1d9b3e5a24"
down_revision: str | None = "e0173070e9cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# RF-13, SUP-31: coordenadas del aeropuerto de cada ciudad del catálogo.
# (codigo, latitud, longitud). Las de Pereira, Bogotá, Cartagena, San Andrés, Madrid, Londres,
# Nueva York, Buenos Aires y Miami son las de referencia del issue #102; las demás salen de
# OurAirports (dominio público). Tunja no tiene código IATA: se usa su aeropuerto (SKTJ).
_COORDENADAS = [
    ("LET", -4.19115, -69.94200),
    ("MDE", 6.16454, -75.42310),
    ("AUC", 7.06888, -70.73690),
    ("BAQ", 10.88960, -74.78080),
    ("CTG", 10.44240, -75.51300),
    ("GUS", 5.54138, -73.34450),
    ("MZL", 5.02960, -75.46470),
    ("FLA", 1.58919, -75.56440),
    ("EYP", 5.31911, -72.38400),
    ("PPN", 2.45436, -76.60925),
    ("VUP", 10.43500, -73.24950),
    ("MTR", 8.82374, -75.82580),
    ("BOG", 4.70160, -74.14690),
    ("UIB", 5.69076, -76.64120),
    ("RCH", 11.52620, -72.92600),
    ("NVA", 2.95015, -75.29400),
    ("SMR", 11.11960, -74.23060),
    ("VVC", 4.16787, -73.61380),
    ("PSO", 1.39672, -77.29093),
    ("CUC", 7.92757, -72.51150),
    ("VGZ", 0.97877, -76.60560),
    ("AXM", 4.45278, -75.76640),
    ("PEI", 4.81270, -75.73950),
    ("ADZ", 12.58360, -81.71120),
    ("BGA", 7.12650, -73.18480),
    ("CZU", 9.33274, -75.28560),
    ("IBE", 4.42161, -75.13330),
    ("CLO", 3.54272, -76.38190),
    ("MVP", 1.25366, -70.23390),
    ("PCR", 6.18472, -67.49320),
    ("PDA", 3.85353, -67.90620),
    ("SJE", 2.57969, -72.63940),
    ("MAD", 40.47190, -3.56260),
    ("LHR", 51.47000, -0.45430),
    ("JFK", 40.64130, -73.77810),
    ("EZE", -34.82220, -58.53580),
    ("MIA", 25.79590, -80.28700),
]


def _tabla_ciudades() -> sa.Table:
    return sa.table(
        "ciudades",
        sa.column("codigo", sa.String),
        sa.column("latitud", sa.Numeric(8, 5)),
        sa.column("longitud", sa.Numeric(8, 5)),
    )


def upgrade() -> None:
    # Las columnas nacen opcionales para poder llenar las 37 ciudades del catálogo.
    op.add_column("ciudades", sa.Column("latitud", sa.Numeric(precision=8, scale=5), nullable=True))
    op.add_column(
        "ciudades", sa.Column("longitud", sa.Numeric(precision=8, scale=5), nullable=True)
    )

    ciudades = _tabla_ciudades()
    for codigo, latitud, longitud in _COORDENADAS:
        op.execute(
            ciudades.update()
            .where(ciudades.c.codigo == op.inline_literal(codigo))
            .values(latitud=op.inline_literal(latitud), longitud=op.inline_literal(longitud))
        )

    op.alter_column("ciudades", "latitud", nullable=False)
    op.alter_column("ciudades", "longitud", nullable=False)


def downgrade() -> None:
    op.drop_column("ciudades", "longitud")
    op.drop_column("ciudades", "latitud")
