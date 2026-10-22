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
from app.modules.vuelos.schemas import (
    CancelacionVueloSalida,
    Capacidad,
    Ciudad,
    CiudadResumen,
    EstadoPromocion,
    EstadoVuelo,
    PaginaPromociones,
    PaginaVuelosAdmin,
    PasajerosVueloSalida,
    Promocion,
    PromocionEntrada,
    SerieVistaPrevia,
    SerieVuelosEntrada,
    SerieVuelosSalida,
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
    raise NoImplementado()


@vuelos.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=VueloAdmin,
    responses=respuestas_error(409),
)
def programar_vuelo(datos: VueloEntrada, usuario: Admin, db: DbSession) -> VueloAdmin:
    """Programa un vuelo, publica su noticia y lo audita (HU-13)."""
    raise NoImplementado()


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
    raise NoImplementado()


@vuelos.post("/recurrentes/vista-previa", response_model=SerieVistaPrevia)
def previsualizar_vuelos_recurrentes(
    datos: SerieVuelosEntrada, usuario: Admin, db: DbSession
) -> SerieVistaPrevia:
    """Fechas que se crearían y las que se omitirían, sin guardar nada (HU-14)."""
    raise NoImplementado()


@vuelos.get("/{vuelo_id}", response_model=VueloDetalle, responses=respuestas_error(404))
def obtener_vuelo(vuelo_id: int, db: DbSession) -> VueloDetalle:
    """Detalle público de un vuelo, con precio vigente y disponibilidad por clase (HU-19)."""
    raise NoImplementado()


@vuelos.get("/{vuelo_id}/gestion", response_model=VueloAdmin, responses=respuestas_error(404))
def obtener_vuelo_gestion(vuelo_id: int, usuario: Admin, db: DbSession) -> VueloAdmin:
    """Vuelo con ocupación y bloqueos de edición, para el formulario de edición (HU-15)."""
    raise NoImplementado()


@vuelos.put("/{vuelo_id}", response_model=VueloAdmin, responses=respuestas_error(404, 409))
def editar_vuelo(vuelo_id: int, datos: VueloEntrada, usuario: Admin, db: DbSession) -> VueloAdmin:
    """Edita un vuelo sin ventas ni reservas activas y conserva su código (HU-15)."""
    raise NoImplementado()


@vuelos.post(
    "/{vuelo_id}/cancelar",
    response_model=CancelacionVueloSalida,
    responses=respuestas_error(404, 409),
)
def cancelar_vuelo(vuelo_id: int, usuario: Admin, db: DbSession) -> CancelacionVueloSalida:
    """Cancela un vuelo sin tiquetes vendidos y anula sus reservas (HU-16, RF-19)."""
    raise NoImplementado()


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
    raise NoImplementado()


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
    raise NoImplementado()


router = APIRouter()
router.include_router(ciudades)
router.include_router(vuelos)
router.include_router(promociones)
