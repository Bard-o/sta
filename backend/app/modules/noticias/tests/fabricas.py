"""Constructores de las noticias para los tests: dataclasses públicas y filas guardadas."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.modules.noticias.models import Noticia
from app.modules.noticias.service import CiudadPublicada, PromocionPublicada, VueloPublicado

ORIGEN = CiudadPublicada(codigo="PEI", nombre="Pereira", zona_horaria="America/Bogota")
DESTINO = CiudadPublicada(codigo="MIA", nombre="Miami", zona_horaria="America/New_York")
SALIDA = datetime(2026, 11, 15, 14, 30, tzinfo=UTC)
# Momento fijo de publicación para los tests de lectura (HU-19).
PUBLICADA_EN = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


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


def guardar_noticia(db: Session, **cambios: Any) -> Noticia:
    """Inserta una noticia de vuelo vigente del vuelo de prueba; `cambios` ajusta sus columnas.

    Se usa para los tests de lectura (HU-19), que necesitan controlar `publicada_en`, la
    vigencia guardada y las fechas de la promoción.
    """
    datos: dict[str, Any] = {
        "tipo": "vuelo",
        "titulo": "Nuevo vuelo Pereira → Miami",
        "publicada_en": PUBLICADA_EN,
        "vigente": True,
        "vuelo_id": 76,
        "vuelo_codigo": "STA-00076",
        "origen_codigo": "PEI",
        "origen_nombre": "Pereira",
        "origen_zona_horaria": "America/Bogota",
        "destino_codigo": "MIA",
        "destino_nombre": "Miami",
        "destino_zona_horaria": "America/New_York",
        "salida": SALIDA,
        "precio_economica": 1_980_000,
        "precio_primera": 4_500_000,
        "imagen_url": "/imagenes/ciudades/MIA.jpg",
    }
    datos.update(cambios)
    noticia = Noticia(**datos)
    db.add(noticia)
    db.flush()
    return noticia


def guardar_promocion(db: Session, **cambios: Any) -> Noticia:
    """Inserta la noticia de una promoción vigente del 30 % en económica; `cambios` la ajusta."""
    datos: dict[str, Any] = {
        "tipo": "promocion",
        "titulo": "Promoción del 30 % en Pereira → Miami, económica",
        "publicada_en": PUBLICADA_EN,
        "vigente": True,
        "promocion_id": 12,
        "promocion_porcentaje": 30,
        "promocion_aplica_economica": True,
        "promocion_aplica_primera": False,
        "promocion_inicio": PUBLICADA_EN - timedelta(days=1),
        "promocion_fin": PUBLICADA_EN + timedelta(days=1),
        "promocion_estado": "programada",
    }
    datos.update(cambios)
    return guardar_noticia(db, **datos)
