"""Interfaz pública del módulo noticias. Otros módulos solo llaman a estas funciones.

Las noticias son automáticas (RF-22, RF-25, RF-55): las publica el módulo vuelos. Noticias
guarda una copia de los datos que muestra y no consulta a vuelos, así que vuelos le avisa de
cada cambio. Ninguna función hace commit: van en la transacción de quien llama.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.noticias import schemas
from app.modules.noticias.models import Noticia

logger = logging.getLogger(__name__)

Clase = Literal["economica", "primera"]
EstadoPromocion = Literal["programada", "vigente", "vencida", "agotada", "cancelada"]

# SUP-06: el carrusel muestra como máximo 10 elementos.
MAX_CARRUSEL = 10

_NOMBRE_CLASE = {"economica": "económica", "primera": "primera"}
_ESTADOS_TERMINALES: tuple[EstadoPromocion, ...] = ("vencida", "agotada", "cancelada")


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


def listar_noticias(
    db: Session,
    *,
    pagina: int = 1,
    por_pagina: int = 10,
    ahora: datetime | None = None,
) -> schemas.PaginaNoticias:
    """Noticias de la más reciente a la más antigua, vigentes y no vigentes (HU-19, RF-55)."""
    momento = ahora or datetime.now(UTC)
    total = db.scalar(select(func.count()).select_from(Noticia)) or 0
    filas = db.scalars(
        select(Noticia)
        .order_by(Noticia.publicada_en.desc(), Noticia.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return schemas.PaginaNoticias(
        items=[_a_noticia(noticia, momento) for noticia in filas],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
    )


def carrusel(db: Session, *, ahora: datetime | None = None) -> list[schemas.Noticia]:
    """Hasta 10 noticias vigentes: primero las promociones y luego los vuelos, de la más
    reciente a la más antigua y con cada vuelo una sola vez (HU-19, RF-22, SUP-06, SUP-41)."""
    momento = ahora or datetime.now(UTC)
    candidatas = sorted(
        db.scalars(select(Noticia).where(Noticia.vigente.is_(True))).all(),
        key=lambda noticia: (noticia.publicada_en, noticia.id),
        reverse=True,
    )
    vigentes = [noticia for noticia in candidatas if _es_vigente(noticia, momento)]
    # Las promociones van delante y ganan sobre la noticia del mismo vuelo.
    promociones = [noticia for noticia in vigentes if noticia.tipo == "promocion"]
    vuelos = [noticia for noticia in vigentes if noticia.tipo == "vuelo"]

    seleccion: list[Noticia] = []
    vistos: set[int] = set()
    for noticia in (*promociones, *vuelos):
        if noticia.vuelo_id in vistos:
            continue
        vistos.add(noticia.vuelo_id)
        seleccion.append(noticia)
        if len(seleccion) == MAX_CARRUSEL:
            break
    return [_a_noticia(noticia, momento) for noticia in seleccion]


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


def _a_noticia(noticia: Noticia, ahora: datetime) -> schemas.Noticia:
    """Vista pública de una noticia, con la vigencia y el estado calculados al consultar."""
    promocion = None
    if noticia.tipo == "promocion":
        porcentaje = noticia.promocion_porcentaje or 0
        promocion = schemas.PromocionNoticia(
            porcentaje=porcentaje,
            clases=_clases_guardadas(noticia),
            inicio=cast(datetime, noticia.promocion_inicio),
            fin=cast(datetime, noticia.promocion_fin),
            estado=_estado_promocion(noticia, ahora),
            # RF-24: el precio con descuento se redondea hacia abajo al peso.
            precio_economica=(
                _precio_con_descuento(noticia.precio_economica, porcentaje)
                if noticia.promocion_aplica_economica
                else None
            ),
            precio_primera=(
                _precio_con_descuento(noticia.precio_primera, porcentaje)
                if noticia.promocion_aplica_primera
                else None
            ),
        )
    return schemas.Noticia(
        id=noticia.id,
        tipo=noticia.tipo,
        titulo=noticia.titulo,
        publicada_en=noticia.publicada_en,
        vigente=_es_vigente(noticia, ahora),
        vuelo_id=noticia.vuelo_id,
        vuelo_codigo=noticia.vuelo_codigo,
        origen=schemas.CiudadNoticia(
            codigo=noticia.origen_codigo,
            nombre=noticia.origen_nombre,
            zona_horaria=noticia.origen_zona_horaria,
        ),
        destino=schemas.CiudadNoticia(
            codigo=noticia.destino_codigo,
            nombre=noticia.destino_nombre,
            zona_horaria=noticia.destino_zona_horaria,
        ),
        salida=noticia.salida,
        precio_economica=noticia.precio_economica,
        precio_primera=noticia.precio_primera,
        imagen_url=noticia.imagen_url,
        promocion=promocion,
    )


def _es_vigente(noticia: Noticia, ahora: datetime) -> bool:
    """RF-25: un vuelo sigue vigente mientras no se retire; una promoción, además, mientras
    haya empezado y no haya terminado."""
    if not noticia.vigente:
        return False
    return noticia.tipo == "vuelo" or _estado_promocion(noticia, ahora) == "vigente"


def _estado_promocion(noticia: Noticia, ahora: datetime) -> EstadoPromocion:
    """Estado efectivo: el guardado solo retiene el final anticipado; el resto se deriva de
    las fechas (RF-23, RF-25)."""
    if noticia.promocion_estado in _ESTADOS_TERMINALES:
        return cast(EstadoPromocion, noticia.promocion_estado)
    inicio = noticia.promocion_inicio
    fin = noticia.promocion_fin
    if inicio is None or fin is None:
        return "vencida"
    if ahora < inicio:
        return "programada"
    if ahora < fin:
        return "vigente"
    return "vencida"


def _precio_con_descuento(precio: int, porcentaje: int) -> int:
    return precio * (100 - porcentaje) // 100


def _encolar_correo_suscriptores(db: Session, noticia: Noticia) -> None:
    """Punto de encolado del correo a los suscriptores (RF-56, issue #32).

    Aún no envía nada: la cola de `core/` y `usuarios.suscriptores_noticias` llegan con ese
    issue. Se llama dentro de la transacción de quien publica para que un rollback no deje
    correos encolados.
    """
    logger.debug("Correo a suscriptores pendiente para la noticia %s (RF-56)", noticia.id)
