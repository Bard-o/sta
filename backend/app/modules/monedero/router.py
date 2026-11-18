"""Endpoints del módulo monedero. Contrato: docs/api/iteracion-2.md (HU-28 a HU-31).

Comprueban la sesión, el rol y el cuerpo; la lógica de tarjetas, recargas, saldo y movimientos
vive en `service.py`. Todo es solo del cliente y cada cliente ve únicamente lo suyo.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import UsuarioActual, require_role
from app.core.db import DbSession
from app.core.errors import respuestas_error
from app.core.security import Rol
from app.modules.monedero import service
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
    return Monedero(saldo=service.saldo_de(db, usuario.id))


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
    return service.listar_movimientos(
        db,
        usuario.id,
        tipo=tipo,
        desde=desde,
        hasta=hasta,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.get("/tarjetas", response_model=list[Tarjeta])
def listar_tarjetas(usuario: Cliente, db: DbSession) -> list[Tarjeta]:
    """Tarjetas registradas y no eliminadas, enmascaradas (HU-29, RF-46)."""
    return service.listar_tarjetas(db, usuario.id)


@router.post("/tarjetas", status_code=status.HTTP_201_CREATED, response_model=Tarjeta)
def registrar_tarjeta(datos: TarjetaEntrada, usuario: Cliente, db: DbSession) -> Tarjeta:
    """Registra una tarjeta simulada: Luhn y vencimiento; guarda solo los últimos 4 (HU-28)."""
    tarjeta = service.registrar_tarjeta(db, usuario.id, datos)
    db.commit()
    return tarjeta


@router.delete(
    "/tarjetas/{tarjeta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=respuestas_error(404),
)
def eliminar_tarjeta(tarjeta_id: int, usuario: Cliente, db: DbSession) -> None:
    """Elimina una tarjeta; sus recargas conservan la referencia (HU-29)."""
    service.eliminar_tarjeta(db, usuario.id, tarjeta_id)
    db.commit()


@router.post(
    "/recargas",
    status_code=status.HTTP_201_CREATED,
    response_model=Movimiento,
    responses=respuestas_error(404),
)
def recargar_monedero(datos: RecargaEntrada, usuario: Cliente, db: DbSession) -> Movimiento:
    """Recarga el monedero desde una tarjeta vigente; aprobación simulada (HU-30, RF-47)."""
    movimiento = service.recargar(db, usuario.id, datos)
    db.commit()
    return movimiento
