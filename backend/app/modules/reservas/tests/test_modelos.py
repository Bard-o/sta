"""Restricciones de la base de datos del modelo de reservas (RF-34, RF-42)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.reservas.models import Tiquete, Tramo
from app.modules.reservas.tests.fabricas import (
    crear_compra,
    crear_tiquete,
    crear_tramo,
    crear_transaccion,
    crear_viajero,
)
from app.modules.vuelos.tests.fabricas import crear_vuelo

SALIDA = datetime(2099, 1, 15, 10, 0, tzinfo=UTC)


def _primer_tiquete(db: Session, transaccion_id: int) -> Tiquete:
    tiquete = db.scalar(
        select(Tiquete)
        .join(Tramo, Tiquete.tramo_id == Tramo.id)
        .where(Tramo.transaccion_id == transaccion_id)
        .order_by(Tiquete.id)
    )
    assert tiquete is not None
    return tiquete


def test_rf42_la_base_rechaza_dos_tiquetes_activos_en_la_misma_silla(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-42 · HU-25: aunque dos peticiones lleguen a la vez, la base de datos solo admite
    una silla activa por vuelo."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_silla")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra_uno = crear_compra(db, cliente.id, vuelo, cantidad=1)
    tiquete_uno = _primer_tiquete(db, compra_uno.id)

    compra_dos = crear_compra(db, cliente.id, vuelo, cantidad=1)
    tramo_dos = db.scalar(select(Tramo).where(Tramo.transaccion_id == compra_dos.id))
    assert tramo_dos is not None
    viajero = crear_viajero(db, compra_dos)

    with pytest.raises(IntegrityError), db.begin_nested():
        crear_tiquete(
            db,
            tramo_dos,
            viajero,
            vuelo=vuelo,
            numero_silla=tiquete_uno.numero_silla,
        )


def test_rf34_la_base_rechaza_dos_tiquetes_activos_con_el_mismo_documento(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-34 · HU-24: el índice único parcial impide el mismo documento activo en el vuelo,
    aunque pertenezca a otra transacción."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_documento")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_compra(db, cliente.id, vuelo, cantidad=1, numero_documento="123456")

    compra_dos = crear_compra(db, cliente.id, vuelo, cantidad=1, numero_documento="654321")
    tramo_dos = db.scalar(select(Tramo).where(Tramo.transaccion_id == compra_dos.id))
    assert tramo_dos is not None
    viajero = crear_viajero(db, compra_dos, numero_documento="123456")

    with pytest.raises(IntegrityError), db.begin_nested():
        crear_tiquete(db, tramo_dos, viajero, vuelo=vuelo)


def test_los_tiquetes_cancelados_liberan_la_silla_y_el_documento(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-34, RF-42: un tiquete cancelado no cuenta para los índices únicos parciales, así
    que su silla y su documento pueden volver a usarse."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_libera")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra_uno = crear_compra(db, cliente.id, vuelo, cantidad=1, numero_documento="123456")
    tiquete_uno = _primer_tiquete(db, compra_uno.id)
    tiquete_uno.estado = "cancelado"
    db.flush()

    compra_dos = crear_transaccion(db, cliente.id, tipo="compra", estado="pagada")
    tramo_dos = crear_tramo(db, compra_dos, vuelo)
    viajero = crear_viajero(db, compra_dos, numero_documento="123456")
    crear_tiquete(
        db,
        tramo_dos,
        viajero,
        vuelo=vuelo,
        numero_silla=tiquete_uno.numero_silla,
    )
