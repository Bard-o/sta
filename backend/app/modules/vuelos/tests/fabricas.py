"""Constructores de vuelos para los tests del módulo."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.modules.vuelos.models import EstadoVuelo, TipoVuelo, Vuelo

SALIDA = datetime(2026, 12, 10, 11, 0, tzinfo=UTC)
CAPACIDADES = {"nacional": (25, 125), "internacional": (50, 200)}


def crear_vuelo(
    db: Session,
    *,
    origen: str = "PEI",
    destino: str = "BOG",
    salida: datetime = SALIDA,
    duracion_minutos: int = 50,
    tipo: TipoVuelo = "nacional",
    estado: EstadoVuelo = "programado",
    **cambios: Any,
) -> Vuelo:
    """Inserta un vuelo directamente en la base para probar duplicados y estados."""
    primera, economica = CAPACIDADES[tipo]
    datos: dict[str, Any] = {
        "tipo": tipo,
        "origen_codigo": origen,
        "destino_codigo": destino,
        "salida": salida,
        "duracion_minutos": duracion_minutos,
        "precio_economica": 280_000,
        "precio_primera": 750_000,
        "capacidad_primera": primera,
        "capacidad_economica": economica,
        "estado": estado,
    }
    datos.update(cambios)
    datos["llegada"] = datos["salida"] + timedelta(minutes=datos["duracion_minutos"])

    vuelo = Vuelo(**datos)
    db.add(vuelo)
    db.flush()
    db.refresh(vuelo)
    return vuelo
