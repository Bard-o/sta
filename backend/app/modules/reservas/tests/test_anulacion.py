"""Anulación de reservas y compras al cancelar un vuelo (HU-16, RF-19, RF-42)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import CorreoEnCola
from app.core.security import Rol
from app.modules.reservas import service
from app.modules.reservas.tests.apoyo import AHORA, SALIDA, cliente_verificado, entrada
from app.modules.reservas.tests.fabricas import crear_compra
from app.modules.vuelos import service as vuelos_service
from app.modules.vuelos.tests.fabricas import crear_vuelo


def _correos(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def test_hu16_cancelar_el_vuelo_anula_reservas_y_compras_pendientes(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-16 · RF-19, RF-42: al cancelar el vuelo se anulan las reservas vigentes y las

    compras pendientes: sus tiquetes quedan cancelados, las sillas se liberan y cada cliente
    recibe un correo. El administrador recibe cuántas se anularon.
    """
    cliente_reserva = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_anula_reserva")
    cliente_compra = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_anula_compra")
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="admin_anula")
    vuelo = crear_vuelo(db, salida=SALIDA)

    reserva = service.crear_reserva(db, cliente_reserva.id, entrada([vuelo]), ahora=AHORA)
    compra = crear_compra(
        db,
        cliente_compra.id,
        vuelo,
        estado="pendiente",
        bloqueo_hasta=AHORA + timedelta(hours=1),
        estado_tiquete="bloqueado",
    )

    resultado = vuelos_service.cancelar_vuelo(db, vuelo.id, usuario_id=admin.id, ahora=AHORA)

    assert resultado.reservas_anuladas == 2
    assert resultado.vuelo.vuelo.estado == "cancelado"
    assert reserva.estado == "cancelada"
    assert compra.estado == "cancelada"

    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    assert ocupacion.reservadas_economica == 0
    assert ocupacion.reservas_activas == 0

    correos = _correos(db)
    assert {correo.destinatario for correo in correos} == {
        cliente_reserva.email,
        cliente_compra.email,
    }
    assert all(reserva.codigo in correo.asunto for correo in correos if "reserva" in correo.asunto)


def test_hu16_anular_reservas_del_vuelo_es_idempotente(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-16 · RNF-18: volver a anular el mismo vuelo no encuentra nada y no duplica correos."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_doble_anula")
    vuelo = crear_vuelo(db, salida=SALIDA)
    reserva = service.crear_reserva(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    assert service.anular_reservas_de_vuelo(db, vuelo.id) == 1
    assert service.anular_reservas_de_vuelo(db, vuelo.id) == 0

    assert reserva.estado == "cancelada"
    assert len(_correos(db)) == 1


def test_hu16_una_compra_pagada_no_se_anula_por_esta_via(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-16: `anular_reservas_de_vuelo` solo toca reservas vigentes y compras pendientes; una

    compra pagada tiene otro tratamiento (reembolso, iteración 3).
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_pagada")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra = crear_compra(db, cliente.id, vuelo, estado="pagada", estado_tiquete="comprado")

    assert service.anular_reservas_de_vuelo(db, vuelo.id) == 0

    assert compra.estado == "pagada"
    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    assert ocupacion.vendidas_economica == 1
    assert _correos(db) == []


def test_hu16_un_vuelo_sin_transacciones_no_genera_correos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-16: si no hay reservas ni compras pendientes, no se encola nada."""
    crear_usuario(Rol.ADMIN, nombre_usuario="admin_sin_reservas")
    vuelo = crear_vuelo(db, salida=SALIDA)

    assert service.anular_reservas_de_vuelo(db, vuelo.id) == 0
    assert _correos(db) == []
