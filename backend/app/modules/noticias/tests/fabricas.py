"""Constructores de los dataclasses públicos de noticias para los tests."""

from datetime import UTC, datetime
from typing import Any

from app.modules.noticias.service import CiudadPublicada, PromocionPublicada, VueloPublicado

ORIGEN = CiudadPublicada(codigo="PEI", nombre="Pereira", zona_horaria="America/Bogota")
DESTINO = CiudadPublicada(codigo="MIA", nombre="Miami", zona_horaria="America/New_York")
SALIDA = datetime(2026, 11, 15, 14, 30, tzinfo=UTC)


def vuelo_publicado(**cambios: Any) -> VueloPublicado:
    """Vuelo Pereira → Miami con los datos que copia la noticia (HU-13)."""
    datos: dict[str, Any] = {
        "vuelo_id": 76,
        "codigo": "STA-00076",
        "origen": ORIGEN,
        "destino": DESTINO,
        "salida": SALIDA,
        "precio_economica": 1_980_000,
        "precio_primera": 4_500_000,
        "imagen_url": "/imagenes/ciudades/MIA.jpg",
    }
    datos.update(cambios)
    return VueloPublicado(**datos)


def promocion_publicada(vuelo: VueloPublicado | None = None, **cambios: Any) -> PromocionPublicada:
    """Promoción del 30 % sobre la económica del vuelo de prueba (HU-17)."""
    datos: dict[str, Any] = {
        "promocion_id": 12,
        "vuelo": vuelo or vuelo_publicado(),
        "porcentaje": 30,
        "clases": ("economica",),
        "inicio": datetime(2026, 10, 18, 13, 0, tzinfo=UTC),
        "fin": datetime(2026, 10, 27, 4, 59, tzinfo=UTC),
    }
    datos.update(cambios)
    return PromocionPublicada(**datos)
