"""Interfaz pública del módulo noticias. Otros módulos solo llaman a estas funciones.

Las noticias son automáticas (RF-22, RF-25, RF-55): las publica el módulo vuelos. Noticias
guarda una copia de los datos que muestra y no consulta a vuelos, así que vuelos le avisa de
cada cambio. Ninguna función hace commit: van en la transacción de quien llama.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CiudadPublicada:
    codigo: str
    nombre: str
    zona_horaria: str


@dataclass(frozen=True)
class VueloPublicado:
    vuelo_id: int
    codigo: str
    origen: CiudadPublicada
    destino: CiudadPublicada
    salida: datetime
    precio_economica: int
    precio_primera: int
    imagen_url: str


@dataclass(frozen=True)
class PromocionPublicada:
    promocion_id: int
    vuelo: VueloPublicado
    porcentaje: int
    clases: tuple[Literal["economica", "primera"], ...]
    inicio: datetime
    fin: datetime


def publicar_noticia_vuelo(db: Session, vuelo: VueloPublicado) -> None:
    """Publica la noticia y el elemento del carrusel de un vuelo nuevo (HU-13, RF-22).

    Encola el correo a los suscritos (RF-56): no espera al envío.
    """
    raise NotImplementedError("HU-19")


def publicar_noticia_promocion(db: Session, promocion: PromocionPublicada) -> None:
    """Publica la noticia de una promoción y la destaca en el carrusel (HU-17, RF-25)."""
    raise NotImplementedError("HU-19")


def actualizar_noticias_de_vuelo(db: Session, vuelo: VueloPublicado) -> None:
    """Actualiza los datos del vuelo en sus noticias tras una edición (HU-15)."""
    raise NotImplementedError("HU-19")


def retirar_noticias_de_vuelo(db: Session, vuelo_id: int) -> None:
    """El vuelo dejó de estar programado (cancelado o realizado): sus noticias pierden la
    vigencia y salen del carrusel, pero siguen en el listado (HU-16, HU-18)."""
    raise NotImplementedError("HU-19")


def terminar_noticia_promocion(
    db: Session, promocion_id: int, estado: Literal["agotada", "cancelada"]
) -> None:
    """La promoción terminó antes de su fecha de fin (RF-23, RF-25). El vencimiento por fecha
    no necesita aviso: noticias lo calcula con `fin`."""
    raise NotImplementedError("HU-19")
