"""Endpoints del módulo búsqueda. Contrato: docs/api/iteracion-2.md (HU-20 y HU-21).

Los endpoints que responden NoImplementado (501) son stubs del contrato: ya validan la sesión
opcional y los parámetros, y su implementación llega con el issue #125.
"""

from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.auth import UsuarioOpcional
from app.core.db import DbSession
from app.core.errors import NoImplementado, respuestas_error
from app.modules.busqueda.schemas import Clase, OrdenBusqueda, PaginaVuelosBusqueda, TipoVuelo

Pagina = Annotated[int, Query(ge=1)]
PorPagina = Annotated[int, Query(ge=1, le=100)]
_PATRON_CIUDAD = r"^[A-Z]{3}$"
_FECHA_LOCAL = "Día de salida en la hora local del origen de cada vuelo."
_HORA_LOCAL = "Hora de salida (hh:mm) en la hora local del origen de cada vuelo."
_PRECIO = "COP, sobre el precio vigente de `clase` (o el menor de las dos sin `clase`)."

router = APIRouter(prefix="/busqueda", tags=["busqueda"])


@router.get("/vuelos", response_model=PaginaVuelosBusqueda)
def buscar_vuelos(
    db: DbSession,
    usuario: UsuarioOpcional,
    codigo: Annotated[
        str | None, Query(max_length=20, description="Parte del código, p. ej. STA-0003.")
    ] = None,
    origen: Annotated[str | None, Query(pattern=_PATRON_CIUDAD)] = None,
    destino: Annotated[str | None, Query(pattern=_PATRON_CIUDAD)] = None,
    tipo: TipoVuelo | None = None,
    fecha_desde: Annotated[date | None, Query(description=_FECHA_LOCAL)] = None,
    fecha_hasta: Annotated[date | None, Query(description=_FECHA_LOCAL)] = None,
    hora_desde: Annotated[time | None, Query(description=_HORA_LOCAL)] = None,
    hora_hasta: Annotated[time | None, Query(description=_HORA_LOCAL)] = None,
    duracion_min: Annotated[int | None, Query(ge=0, description="Minutos.")] = None,
    duracion_max: Annotated[int | None, Query(ge=0, description="Minutos.")] = None,
    precio_min: Annotated[int | None, Query(ge=0, description=_PRECIO)] = None,
    precio_max: Annotated[int | None, Query(ge=0, description=_PRECIO)] = None,
    clase: Clase | None = None,
    orden: OrdenBusqueda = "precio",
    pagina: Pagina = 1,
    por_pagina: PorPagina = 20,
) -> PaginaVuelosBusqueda:
    """Vuelos programados y a la venta que cumplen todos los filtros (HU-20, RF-27).

    Público. La primera página de la búsqueda de un cliente se registra (RF-29).
    """
    raise NoImplementado()


@router.get("/regresos", response_model=PaginaVuelosBusqueda, responses=respuestas_error(404))
def buscar_regresos(
    db: DbSession,
    usuario: UsuarioOpcional,
    vuelo_ida_id: Annotated[int, Query(ge=1, description="Vuelo de ida elegido.")],
    destino: Annotated[
        str,
        Query(
            pattern=_PATRON_CIUDAD,
            description="Ciudad de regreso; puede ser distinta del origen de la ida.",
        ),
    ],
    fecha: Annotated[
        date, Query(description="Día de salida del regreso, en la hora local de su origen.")
    ],
    clase: Clase | None = None,
    orden: OrdenBusqueda = "precio",
    pagina: Pagina = 1,
    por_pagina: PorPagina = 20,
) -> PaginaVuelosBusqueda:
    """Regresos desde el destino de la ida que salen después de su llegada (HU-21, RF-28)."""
    raise NoImplementado()
