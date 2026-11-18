"""Restricciones del modelo del carrito (RF-30)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.carrito.models import SeleccionCarrito, TramoSeleccion
from app.modules.carrito.tests.apoyo import crear_cliente
from app.modules.carrito.tests.fabricas import crear_seleccion
from app.modules.vuelos.tests.fabricas import crear_vuelo

SALIDA = datetime(2027, 4, 15, 11, 0, tzinfo=UTC)


def test_una_seleccion_no_admite_cero_viajeros(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-30: el modelo rechaza una selección sin viajeros."""
    cliente = crear_cliente(db, crear_usuario, "cliente_modelo_viajeros")

    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(SeleccionCarrito(cliente_id=cliente.id, viajeros=0))
        db.flush()


def test_un_tramo_exige_precio_y_orden_validos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-30: el precio de referencia es positivo y el orden solo 1 o 2."""
    cliente = crear_cliente(db, crear_usuario, "cliente_modelo_tramo")
    vuelo = crear_vuelo(db, salida=SALIDA)
    seleccion = crear_seleccion(db, cliente.id, [vuelo])

    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            TramoSeleccion(
                seleccion_id=seleccion.id,
                vuelo_id=vuelo.id,
                clase="economica",
                precio_al_agregar=0,
                orden=3,
            )
        )
        db.flush()


def test_no_hay_dos_tramos_con_el_mismo_orden(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-30: una selección tiene un tramo por orden (ida y regreso)."""
    cliente = crear_cliente(db, crear_usuario, "cliente_modelo_orden")
    vuelo = crear_vuelo(db, salida=SALIDA)
    seleccion = crear_seleccion(db, cliente.id, [vuelo])

    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            TramoSeleccion(
                seleccion_id=seleccion.id,
                vuelo_id=vuelo.id,
                clase="primera",
                precio_al_agregar=750_000,
                orden=1,
            )
        )
        db.flush()


def test_quitar_la_seleccion_borra_sus_tramos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-30: el borrado en cascada deja el carrito sin tramos huérfanos."""
    cliente = crear_cliente(db, crear_usuario, "cliente_modelo_cascada")
    ida = crear_vuelo(db, salida=SALIDA)
    regreso = crear_vuelo(
        db, origen="BOG", destino="PEI", salida=datetime(2027, 4, 16, 9, 0, tzinfo=UTC)
    )
    seleccion = crear_seleccion(db, cliente.id, [ida, regreso])

    db.delete(seleccion)
    db.flush()

    assert (
        db.scalar(
            select(func.count(TramoSeleccion.id)).where(TramoSeleccion.seleccion_id == seleccion.id)
        )
        == 0
    )
