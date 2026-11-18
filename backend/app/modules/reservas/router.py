"""Endpoints de reservas, compras y Mis viajes. Contrato: docs/api/iteracion-2.md (HU-24 a HU-27).

Los endpoints que responden NoImplementado (501) son stubs del contrato: ya validan la sesión,
el rol y el cuerpo. Los implementan #118 (reservar), #124 (comprar), #130 (trayecto completo) y
#131 (pagar una reserva y Mis viajes).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import UsuarioActual, require_role
from app.core.db import DbSession
from app.core.errors import NoImplementado, respuestas_error
from app.core.security import Rol
from app.modules.reservas import service
from app.modules.reservas.schemas import (
    EstadoViaje,
    PaginaViajes,
    PagoReservaEntrada,
    PagoReservaSalida,
    TipoViaje,
    Viaje,
    ViajeEntrada,
)

Cliente = Annotated[UsuarioActual, Depends(require_role(Rol.CLIENTE))]
Pagina = Annotated[int, Query(ge=1)]
PorPagina = Annotated[int, Query(ge=1, le=100)]
_FECHA_VIAJE = "Día de salida del primer tramo, en hora de Colombia."

# ---------- Reservas ----------

reservas = APIRouter(prefix="/reservas", tags=["reservas"])


@reservas.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Viaje,
    responses=respuestas_error(409),
)
def reservar(datos: ViajeEntrada, usuario: Cliente, db: DbSession) -> Viaje:
    """Reserva sin pagar: asigna sillas, congela el precio y fija el vencimiento (HU-24, HU-26)."""
    transaccion = service.crear_reserva(db, usuario.id, datos)
    db.commit()
    return service.viaje_de(db, transaccion)


@reservas.post(
    "/{reserva_id}/pagar",
    response_model=PagoReservaSalida,
    responses=respuestas_error(404, 409),
)
def pagar_reserva(
    reserva_id: int, datos: PagoReservaEntrada, usuario: Cliente, db: DbSession
) -> PagoReservaSalida:
    """Paga la reserva completa o algunos viajeros al precio congelado (HU-27, RF-38)."""
    reserva, compra = service.pagar_reserva(db, usuario.id, reserva_id, datos.viajero_ids)
    db.commit()
    return PagoReservaSalida(
        reserva=service.viaje_de(db, reserva), compra=service.viaje_de(db, compra)
    )


# ---------- Compras ----------

compras = APIRouter(prefix="/compras", tags=["reservas"])


@compras.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Viaje,
    responses=respuestas_error(409),
)
def iniciar_compra(datos: ViajeEntrada, usuario: Cliente, db: DbSession) -> Viaje:
    """Asigna las sillas y las bloquea 15 minutos mientras el cliente paga (HU-25, SUP-15)."""
    compra = service.crear_compra(db, usuario.id, datos)
    db.commit()
    return service.viaje_de(db, compra)


@compras.get("/{compra_id}", response_model=Viaje, responses=respuestas_error(404))
def obtener_compra(compra_id: int, usuario: Cliente, db: DbSession) -> Viaje:
    """Una compra del cliente, pendiente, vencida, cancelada o activa (HU-25)."""
    compra = service.obtener_compra(db, usuario.id, compra_id)
    db.commit()
    return service.viaje_de(db, compra)


@compras.post(
    "/{compra_id}/confirmar",
    response_model=Viaje,
    responses=respuestas_error(404, 409),
)
def confirmar_compra(compra_id: int, usuario: Cliente, db: DbSession) -> Viaje:
    """Cobra con el monedero, emite los tiquetes y envía el código y el comprobante (HU-25)."""
    compra = service.confirmar_compra(db, usuario.id, compra_id)
    db.commit()
    return service.viaje_de(db, compra)


@compras.delete(
    "/{compra_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=respuestas_error(404, 409),
)
def soltar_compra(compra_id: int, usuario: Cliente, db: DbSession) -> None:
    """Suelta el bloqueo de una compra pendiente y libera sus sillas (HU-25)."""
    service.soltar_compra(db, usuario.id, compra_id)
    db.commit()


# ---------- Mis viajes ----------

mis_viajes = APIRouter(prefix="/mis-viajes", tags=["reservas"])


@mis_viajes.get("", response_model=PaginaViajes)
def listar_mis_viajes(
    usuario: Cliente,
    db: DbSession,
    tipo: Annotated[TipoViaje, Query(description="Pestaña de S19: reserva o compra.")],
    estado: EstadoViaje | None = None,
    desde: Annotated[date | None, Query(description=_FECHA_VIAJE)] = None,
    hasta: Annotated[date | None, Query(description=_FECHA_VIAJE)] = None,
    pagina: Pagina = 1,
    por_pagina: PorPagina = 20,
) -> PaginaViajes:
    """Reservas o compras del cliente, de la más reciente a la más antigua (HU-27, RF-45)."""
    raise NoImplementado()


router = APIRouter()
router.include_router(reservas)
router.include_router(compras)
router.include_router(mis_viajes)
