"""Endpoints del módulo monedero. Contrato: docs/api/iteracion-2.md (HU-28 a HU-31).

Los endpoints que responden NoImplementado (501) son stubs del contrato: ya validan la sesión,
el rol y el cuerpo, y su implementación llega con el issue #119.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import UsuarioActual, require_role
from app.core.db import DbSession
from app.core.errors import NoImplementado, respuestas_error
from app.core.security import Rol
from app.modules.monedero.schemas import (
    Monedero,
    Movimiento,
    PaginaMovimientos,
    RecargaEntrada,
    Tarjeta,
    TarjetaEntrada,
    TipoMovimiento,
)

Cliente = Annotated[UsuarioActual, Depends(require_role(Rol.CLIENTE))]
Pagina = Annotated[int, Query(ge=1)]
PorPagina = Annotated[int, Query(ge=1, le=100)]
_FECHA_MOVIMIENTO = "Fecha del movimiento en hora de Colombia."

router = APIRouter(prefix="/monedero", tags=["monedero"])


@router.get("", response_model=Monedero)
def consultar_saldo(usuario: Cliente, db: DbSession) -> Monedero:
    """Saldo del monedero (HU-31, RF-48)."""
    raise NoImplementado()


@router.get("/movimientos", response_model=PaginaMovimientos)
def listar_movimientos(
    usuario: Cliente,
    db: DbSession,
    tipo: TipoMovimiento | None = None,
    desde: Annotated[date | None, Query(description=_FECHA_MOVIMIENTO)] = None,
    hasta: Annotated[date | None, Query(description=_FECHA_MOVIMIENTO)] = None,
    pagina: Pagina = 1,
    por_pagina: PorPagina = 20,
) -> PaginaMovimientos:
    """Movimientos del más reciente al más antiguo, con filtros por tipo y fecha (HU-31)."""
    raise NoImplementado()


@router.get("/tarjetas", response_model=list[Tarjeta])
def listar_tarjetas(usuario: Cliente, db: DbSession) -> list[Tarjeta]:
    """Tarjetas registradas y no eliminadas, enmascaradas (HU-29, RF-46)."""
    raise NoImplementado()


@router.post("/tarjetas", status_code=status.HTTP_201_CREATED, response_model=Tarjeta)
def registrar_tarjeta(datos: TarjetaEntrada, usuario: Cliente, db: DbSession) -> Tarjeta:
    """Registra una tarjeta simulada: Luhn y vencimiento; guarda solo los últimos 4 (HU-28)."""
    raise NoImplementado()


@router.delete(
    "/tarjetas/{tarjeta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=respuestas_error(404),
)
def eliminar_tarjeta(tarjeta_id: int, usuario: Cliente, db: DbSession) -> None:
    """Elimina una tarjeta; sus recargas conservan la referencia (HU-29)."""
    raise NoImplementado()


@router.post(
    "/recargas",
    status_code=status.HTTP_201_CREATED,
    response_model=Movimiento,
    responses=respuestas_error(404),
)
def recargar_monedero(datos: RecargaEntrada, usuario: Cliente, db: DbSession) -> Movimiento:
    """Recarga el monedero desde una tarjeta vigente; aprobación simulada (HU-30, RF-47)."""
    raise NoImplementado()
