"""Endpoints del módulo vuelos. Contrato: docs/api/iteracion-1.md (HU-13 a HU-18).

Los endpoints que responden NoImplementado (501) son stubs del contrato: ya validan el rol y
el cuerpo, y su implementación llega con el issue de cada HU.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import UsuarioActual, require_role
from app.core.db import DbSession
from app.core.errors import NoImplementado, respuestas_error
from app.core.security import Rol
from app.modules.vuelos import service
from app.modules.vuelos.models import Ciudad as CiudadModelo
from app.modules.vuelos.models import Vuelo as VueloModelo
from app.modules.vuelos.schemas import (
    CancelacionVueloSalida,
    Capacidad,
    Ciudad,
    CiudadResumen,
    ClaseDetalle,
    EstadoPromocion,
    EstadoVuelo,
    FechaOmitida,
    Ocupacion,
    OcupacionClase,
    PaginaPromociones,
    PaginaVuelosAdmin,
    PasajerosVueloSalida,
    Promocion,
    PromocionEntrada,
    PromocionResumen,
    SerieVistaPrevia,
    SerieVuelosEntrada,
    SerieVuelosSalida,
    Vuelo,
    VueloAdmin,
    VueloDetalle,
    VueloEntrada,
    VueloVistaPrevia,
)

Admin = Annotated[UsuarioActual, Depends(require_role(Rol.ADMIN))]
Pagina = Annotated[int, Query(ge=1)]
PorPagina = Annotated[int, Query(ge=1, le=100)]
_FECHA_FILTRO = "Salida (programados, cancelados) o llegada (realizados), en hora de Colombia."

# ---------- Ciudades ----------

ciudades = APIRouter(prefix="/ciudades", tags=["vuelos"])


@ciudades.get("", response_model=list[Ciudad])
def listar_ciudades(db: DbSession) -> list[Ciudad]:
    """Catálogo de ciudades (RF-12). Público: lo usan el formulario de vuelos y la búsqueda."""
    return service.listar_ciudades(db)


# ---------- Vuelos ----------

vuelos = APIRouter(prefix="/vuelos", tags=["vuelos"])


@vuelos.get("", response_model=PaginaVuelosAdmin)
def listar_vuelos(
    usuario: Admin,
    db: DbSession,
    estado: EstadoVuelo = "programado",
    desde: Annotated[date | None, Query(description=_FECHA_FILTRO)] = None,
    hasta: Annotated[date | None, Query(description=_FECHA_FILTRO)] = None,
    q: Annotated[str | None, Query(max_length=60, description="Código o ciudad.")] = None,
    pagina: Pagina = 1,
    por_pagina: PorPagina = 20,
) -> PaginaVuelosAdmin:
    """Vuelos para el administrador (HU-15, HU-16, HU-18).

    Programados por salida ascendente; realizados y cancelados por fecha descendente.
    """
    pagina_vuelos = service.listar_vuelos_gestion(
        db,
        estado=estado,
        desde=desde,
        hasta=hasta,
        q=q,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return PaginaVuelosAdmin(
        items=[_a_vuelo_admin(item) for item in pagina_vuelos.items],
        total=pagina_vuelos.total,
        pagina=pagina_vuelos.pagina,
        por_pagina=pagina_vuelos.por_pagina,
    )


@vuelos.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=VueloAdmin,
    responses=respuestas_error(409),
)
def programar_vuelo(datos: VueloEntrada, usuario: Admin, db: DbSession) -> VueloAdmin:
    """Programa un vuelo, publica su noticia y lo audita (HU-13)."""
    try:
        programado = service.programar_vuelo(db, datos, usuario_id=usuario.id)
        db.commit()
    except Exception:
        # RNF-17: si falla la noticia o la auditoría no queda nada del vuelo.
        db.rollback()
        raise
    return _a_vuelo_admin(programado)


def _a_vuelo_admin(gestion: service.VueloGestion) -> VueloAdmin:
    """Vista del administrador: ocupación, bloqueos y promociones del vuelo (HU-15)."""
    vuelo = gestion.vuelo
    ocupacion = gestion.ocupacion
    return VueloAdmin(
        id=vuelo.id,
        codigo=vuelo.codigo,
        tipo=vuelo.tipo,
        origen=CiudadResumen.model_validate(gestion.origen),
        destino=CiudadResumen.model_validate(gestion.destino),
        salida=vuelo.salida,
        llegada=vuelo.llegada,
        duracion_minutos=vuelo.duracion_minutos,
        precio_economica=vuelo.precio_economica,
        precio_primera=vuelo.precio_primera,
        capacidad=Capacidad(
            primera=vuelo.capacidad_primera,
            economica=vuelo.capacidad_economica,
            total=vuelo.capacidad_primera + vuelo.capacidad_economica,
        ),
        estado=vuelo.estado,
        ocupacion=Ocupacion(
            primera=_ocupacion_clase(
                vuelo.capacidad_primera,
                ocupacion.vendidas_primera,
                ocupacion.reservadas_primera,
            ),
            economica=_ocupacion_clase(
                vuelo.capacidad_economica,
                ocupacion.vendidas_economica,
                ocupacion.reservadas_economica,
            ),
        ),
        reservas_activas=ocupacion.reservas_activas,
        tiquetes_vendidos=ocupacion.tiquetes_vendidos,
        editable=gestion.editable,
        motivo_no_editable=gestion.motivo_no_editable,
        cancelable=gestion.cancelable,
        promociones=[],
    )


def _ocupacion_clase(capacidad: int, vendidas: int, reservadas: int) -> OcupacionClase:
    return OcupacionClase(
        capacidad=capacidad,
        vendidas=vendidas,
        reservadas=reservadas,
        disponibles=capacidad - vendidas - reservadas,
    )


@vuelos.post("/vista-previa", response_model=VueloVistaPrevia, responses=respuestas_error(409))
def previsualizar_vuelo(datos: VueloEntrada, usuario: Admin, db: DbSession) -> VueloVistaPrevia:
    """Valida el vuelo y calcula tipo, capacidad y llegada sin guardarlo (HU-13)."""
    calculado = service.previsualizar_vuelo(db, datos)
    return VueloVistaPrevia(
        tipo=calculado.tipo,
        origen=CiudadResumen.model_validate(calculado.origen),
        destino=CiudadResumen.model_validate(calculado.destino),
        salida=calculado.salida,
        llegada=calculado.llegada,
        duracion_minutos=calculado.duracion_minutos,
        capacidad=Capacidad(
            primera=calculado.capacidad_primera,
            economica=calculado.capacidad_economica,
            total=calculado.capacidad_total,
        ),
    )


@vuelos.post("/recurrentes", status_code=status.HTTP_201_CREATED, response_model=SerieVuelosSalida)
def programar_vuelos_recurrentes(
    datos: SerieVuelosEntrada, usuario: Admin, db: DbSession
) -> SerieVuelosSalida:
    """Crea un vuelo independiente por cada fecha de la serie (HU-14)."""
    try:
        serie = service.programar_serie(db, datos, usuario_id=usuario.id)
        db.commit()
    except Exception:
        # RNF-17: si falla una ocurrencia no queda ninguna de la serie.
        db.rollback()
        raise
    return SerieVuelosSalida(
        creados=[_a_vuelo(vuelo, serie.origen, serie.destino) for vuelo in serie.creados],
        omitidas=_a_omitidas(serie.omitidas),
    )


@vuelos.post("/recurrentes/vista-previa", response_model=SerieVistaPrevia)
def previsualizar_vuelos_recurrentes(
    datos: SerieVuelosEntrada, usuario: Admin, db: DbSession
) -> SerieVistaPrevia:
    """Fechas que se crearían y las que se omitirían, sin guardar nada (HU-14)."""
    serie = service.previsualizar_serie(db, datos)
    capacidad_primera, capacidad_economica = service.capacidad_de(serie.tipo)
    return SerieVistaPrevia(
        tipo=serie.tipo,
        capacidad=Capacidad(
            primera=capacidad_primera,
            economica=capacidad_economica,
            total=capacidad_primera + capacidad_economica,
        ),
        fechas=serie.fechas,
        omitidas=_a_omitidas(serie.omitidas),
    )


def _a_omitidas(omitidas: list[service.OcurrenciaOmitida]) -> list[FechaOmitida]:
    return [
        FechaOmitida(fecha=omitida.fecha, codigo=omitida.codigo, motivo=omitida.motivo)
        for omitida in omitidas
    ]


def _a_vuelo(vuelo: VueloModelo, origen: CiudadModelo, destino: CiudadModelo) -> Vuelo:
    """Forma pública de un vuelo de la serie, sin ocupación ni bloqueos."""
    return Vuelo(
        id=vuelo.id,
        codigo=vuelo.codigo,
        tipo=vuelo.tipo,
        origen=CiudadResumen.model_validate(origen),
        destino=CiudadResumen.model_validate(destino),
        salida=vuelo.salida,
        llegada=vuelo.llegada,
        duracion_minutos=vuelo.duracion_minutos,
        precio_economica=vuelo.precio_economica,
        precio_primera=vuelo.precio_primera,
        capacidad=Capacidad(
            primera=vuelo.capacidad_primera,
            economica=vuelo.capacidad_economica,
            total=vuelo.capacidad_primera + vuelo.capacidad_economica,
        ),
        estado=vuelo.estado,
    )


@vuelos.get("/{vuelo_id}", response_model=VueloDetalle, responses=respuestas_error(404))
def obtener_vuelo(vuelo_id: int, db: DbSession) -> VueloDetalle:
    """Detalle público de un vuelo, con precio vigente y disponibilidad por clase (HU-19)."""
    return _a_vuelo_detalle(service.obtener_vuelo_detalle(db, vuelo_id))


def _a_vuelo_detalle(detalle: service.VueloDetalleGestion) -> VueloDetalle:
    """Los datos del vuelo más el precio y las sillas de cada clase (HU-19)."""
    base = _a_vuelo(detalle.vuelo, detalle.origen, detalle.destino)
    return VueloDetalle(
        **base.model_dump(),
        economica=_a_clase_detalle(detalle.economica),
        primera=_a_clase_detalle(detalle.primera),
    )


def _a_clase_detalle(clase: service.ClaseDetalleVuelo) -> ClaseDetalle:
    promocion = clase.promocion
    return ClaseDetalle(
        precio_base=clase.precio_base,
        precio_vigente=clase.precio,
        promocion=(
            None
            if promocion is None
            else PromocionResumen(
                id=promocion.id,
                porcentaje=promocion.porcentaje,
                clases=promocion.clases,
                inicio=promocion.inicio,
                fin=promocion.fin,
                estado=promocion.estado,
            )
        ),
        disponibles=clase.disponibles,
        agotada=clase.agotada,
    )


@vuelos.get("/{vuelo_id}/gestion", response_model=VueloAdmin, responses=respuestas_error(404))
def obtener_vuelo_gestion(vuelo_id: int, usuario: Admin, db: DbSession) -> VueloAdmin:
    """Vuelo con ocupación y bloqueos de edición, para el formulario de edición (HU-15)."""
    return _a_vuelo_admin(service.obtener_vuelo_gestion(db, vuelo_id))


@vuelos.put("/{vuelo_id}", response_model=VueloAdmin, responses=respuestas_error(404, 409))
def editar_vuelo(vuelo_id: int, datos: VueloEntrada, usuario: Admin, db: DbSession) -> VueloAdmin:
    """Edita un vuelo sin ventas ni reservas activas y conserva su código (HU-15)."""
    try:
        editado = service.editar_vuelo(db, vuelo_id, datos, usuario_id=usuario.id)
        db.commit()
    except Exception:
        # RNF-17: si falla la noticia o la auditoría no queda nada del cambio.
        db.rollback()
        raise
    return _a_vuelo_admin(editado)


@vuelos.post(
    "/{vuelo_id}/cancelar",
    response_model=CancelacionVueloSalida,
    responses=respuestas_error(404, 409),
)
def cancelar_vuelo(vuelo_id: int, usuario: Admin, db: DbSession) -> CancelacionVueloSalida:
    """Cancela un vuelo sin tiquetes vendidos y anula sus reservas (HU-16, RF-19)."""
    try:
        cancelado = service.cancelar_vuelo(db, vuelo_id, usuario_id=usuario.id)
        db.commit()
    except Exception:
        # RNF-17: si falla la anulación, la noticia o la auditoría no queda nada del cambio.
        db.rollback()
        raise
    return CancelacionVueloSalida(
        vuelo=_a_vuelo_admin(cancelado.vuelo),
        reservas_anuladas=cancelado.reservas_anuladas,
    )


@vuelos.get(
    "/{vuelo_id}/pasajeros",
    response_model=PasajerosVueloSalida,
    responses=respuestas_error(404),
)
def listar_pasajeros_vuelo(vuelo_id: int, usuario: Admin, db: DbSession) -> PasajerosVueloSalida:
    """Pasajeros con clase y silla, y ocupación por clase (HU-18)."""
    raise NoImplementado()


@vuelos.post(
    "/{vuelo_id}/promociones",
    status_code=status.HTTP_201_CREATED,
    response_model=Promocion,
    responses=respuestas_error(404, 409),
)
def crear_promocion(
    vuelo_id: int, datos: PromocionEntrada, usuario: Admin, db: DbSession
) -> Promocion:
    """Crea una promoción, publica su noticia y la audita (HU-17, RF-23)."""
    try:
        creada = service.crear_promocion(db, vuelo_id, datos, usuario_id=usuario.id)
        db.commit()
    except Exception:
        # RNF-17: si falla la noticia o la auditoría no queda nada de la promoción.
        db.rollback()
        raise
    return _a_promocion(creada)


def _a_promocion(gestion: service.PromocionGestion) -> Promocion:
    """Forma pública de la promoción, con el vuelo y su estado efectivo (HU-17)."""
    promocion = gestion.promocion
    return Promocion(
        id=promocion.id,
        porcentaje=promocion.porcentaje,
        clases=gestion.clases,
        inicio=promocion.inicio,
        fin=promocion.fin,
        estado=gestion.estado,
        vuelo_id=gestion.vuelo.id,
        vuelo_codigo=gestion.vuelo.codigo,
        origen=CiudadResumen.model_validate(gestion.origen),
        destino=CiudadResumen.model_validate(gestion.destino),
        salida=gestion.vuelo.salida,
        creada_en=promocion.creada_en,
    )


# ---------- Promociones ----------

promociones = APIRouter(prefix="/promociones", tags=["vuelos"])


@promociones.get("", response_model=PaginaPromociones)
def listar_promociones(
    usuario: Admin,
    db: DbSession,
    estado: EstadoPromocion | None = None,
    pagina: Pagina = 1,
    por_pagina: PorPagina = 20,
) -> PaginaPromociones:
    """Promociones de todos los vuelos, las más recientes primero (HU-17)."""
    pagina_promociones = service.listar_promociones(
        db, estado=estado, pagina=pagina, por_pagina=por_pagina
    )
    return PaginaPromociones(
        items=[_a_promocion(item) for item in pagina_promociones.items],
        total=pagina_promociones.total,
        pagina=pagina_promociones.pagina,
        por_pagina=pagina_promociones.por_pagina,
    )


router = APIRouter()
router.include_router(ciudades)
router.include_router(vuelos)
router.include_router(promociones)
