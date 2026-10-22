"""Interfaz pública del módulo noticias. Otros módulos solo llaman a estas funciones.

Las noticias son automáticas (RF-22, RF-25, RF-55): las publica el módulo vuelos. Noticias
guarda una copia de los datos que muestra y no consulta a vuelos, así que vuelos le avisa de
cada cambio. Ninguna función hace commit: van en la transacción de quien llama.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.noticias.models import Noticia

logger = logging.getLogger(__name__)

Clase = Literal["economica", "primera"]

_NOMBRE_CLASE = {"economica": "económica", "primera": "primera"}


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
    noticia = Noticia(tipo="vuelo", titulo=_titulo_vuelo(vuelo), **_datos_de_vuelo(vuelo))
    db.add(noticia)
    # Deja la noticia con id para el enlace del correo de los suscritos (RF-56).
    db.flush()
    _encolar_correo_suscriptores(db, noticia)


def publicar_noticia_promocion(db: Session, promocion: PromocionPublicada) -> None:
    """Publica la noticia de una promoción y la destaca en el carrusel (HU-17, RF-25)."""
    clases = set(promocion.clases)
    noticia = Noticia(
        tipo="promocion",
        titulo=_titulo_promocion(
            origen=promocion.vuelo.origen.nombre,
            destino=promocion.vuelo.destino.nombre,
            porcentaje=promocion.porcentaje,
            clases=promocion.clases,
        ),
        promocion_id=promocion.promocion_id,
        promocion_porcentaje=promocion.porcentaje,
        promocion_aplica_economica="economica" in clases,
        promocion_aplica_primera="primera" in clases,
        promocion_inicio=promocion.inicio,
        promocion_fin=promocion.fin,
        promocion_estado="programada",
        **_datos_de_vuelo(promocion.vuelo),
    )
    db.add(noticia)
    db.flush()
    _encolar_correo_suscriptores(db, noticia)


def actualizar_noticias_de_vuelo(db: Session, vuelo: VueloPublicado) -> None:
    """Actualiza los datos del vuelo en sus noticias tras una edición (HU-15)."""
    datos = _datos_de_vuelo(vuelo)
    for noticia in _noticias_de_vuelo(db, vuelo.vuelo_id):
        for campo, valor in datos.items():
            setattr(noticia, campo, valor)
        if noticia.tipo == "vuelo":
            noticia.titulo = _titulo_vuelo(vuelo)
        else:
            noticia.titulo = _titulo_promocion(
                origen=vuelo.origen.nombre,
                destino=vuelo.destino.nombre,
                porcentaje=noticia.promocion_porcentaje or 0,
                clases=_clases_guardadas(noticia),
            )


def retirar_noticias_de_vuelo(db: Session, vuelo_id: int) -> None:
    """El vuelo dejó de estar programado (cancelado o realizado): sus noticias pierden la
    vigencia y salen del carrusel, pero siguen en el listado (HU-16, HU-18)."""
    for noticia in _noticias_de_vuelo(db, vuelo_id):
        noticia.vigente = False


def terminar_noticia_promocion(
    db: Session, promocion_id: int, estado: Literal["agotada", "cancelada"]
) -> None:
    """La promoción terminó antes de su fecha de fin (RF-23, RF-25). El vencimiento por fecha
    no necesita aviso: noticias lo calcula con `fin`."""
    noticias = db.scalars(select(Noticia).where(Noticia.promocion_id == promocion_id)).all()
    for noticia in noticias:
        noticia.vigente = False
        noticia.promocion_estado = estado


def _noticias_de_vuelo(db: Session, vuelo_id: int) -> list[Noticia]:
    return list(db.scalars(select(Noticia).where(Noticia.vuelo_id == vuelo_id)))


def _datos_de_vuelo(vuelo: VueloPublicado) -> dict[str, object]:
    """Copia de los datos del vuelo que muestra la noticia (RF-22)."""
    return {
        "vuelo_id": vuelo.vuelo_id,
        "vuelo_codigo": vuelo.codigo,
        "origen_codigo": vuelo.origen.codigo,
        "origen_nombre": vuelo.origen.nombre,
        "origen_zona_horaria": vuelo.origen.zona_horaria,
        "destino_codigo": vuelo.destino.codigo,
        "destino_nombre": vuelo.destino.nombre,
        "destino_zona_horaria": vuelo.destino.zona_horaria,
        "salida": vuelo.salida,
        "precio_economica": vuelo.precio_economica,
        "precio_primera": vuelo.precio_primera,
        "imagen_url": vuelo.imagen_url,
    }


def _titulo_vuelo(vuelo: VueloPublicado) -> str:
    return f"Nuevo vuelo {vuelo.origen.nombre} → {vuelo.destino.nombre}"


def _titulo_promocion(
    *,
    origen: str,
    destino: str,
    porcentaje: int,
    clases: Iterable[Clase],
) -> str:
    nombres = " y ".join(_NOMBRE_CLASE[clase] for clase in clases)
    return f"Promoción del {porcentaje} % en {origen} → {destino}, {nombres}"


def _clases_guardadas(noticia: Noticia) -> list[Clase]:
    clases: list[Clase] = []
    if noticia.promocion_aplica_economica:
        clases.append("economica")
    if noticia.promocion_aplica_primera:
        clases.append("primera")
    return clases


def _encolar_correo_suscriptores(db: Session, noticia: Noticia) -> None:
    """Punto de encolado del correo a los suscriptores (RF-56, issue #32).

    Aún no envía nada: la cola de `core/` y `usuarios.suscriptores_noticias` llegan con ese
    issue. Se llama dentro de la transacción de quien publica para que un rollback no deje
    correos encolados.
    """
    logger.debug("Correo a suscriptores pendiente para la noticia %s (RF-56)", noticia.id)
