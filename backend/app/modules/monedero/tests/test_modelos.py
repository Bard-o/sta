"""Modelos del monedero: RNF-12 y restricciones de RF-48."""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.monedero.models import Movimiento, Tarjeta
from app.modules.monedero.tests.fabricas import crear_tarjeta

COLUMNAS_TARJETA = {
    "id",
    "cliente_id",
    "tipo",
    "franquicia",
    "titular",
    "ultimos_4",
    "token",
    "vencimiento",
    "eliminada",
    "creado_en",
    "actualizado_en",
}


def test_rnf12_la_tabla_de_tarjetas_solo_guarda_ultimos_4_y_token(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RNF-12, HU-28, RF-46: no hay columna para el número completo ni para el CVV.

    Solo se persisten los últimos cuatro dígitos y el token simulado; ningún valor guardado
    tiene un número de tarjeta completo.
    """
    assert set(Tarjeta.__table__.columns.keys()) == COLUMNAS_TARJETA
    assert not {"numero", "numero_completo", "cvv"} & set(Tarjeta.__table__.columns.keys())

    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_rnf12", email="rnf12@example.com")
    crear_tarjeta(db, cliente.id, ultimos_4="4242")

    guardada = db.scalars(select(Tarjeta)).one()
    assert guardada.ultimos_4 == "4242"
    assert guardada.token
    for nombre in COLUMNAS_TARJETA:
        valor = getattr(guardada, nombre)
        assert not (isinstance(valor, str) and valor.isdigit() and len(valor) >= 13)


def test_rf48_la_base_rechaza_un_saldo_resultante_negativo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-48: un movimiento no puede dejar el saldo en negativo."""
    cliente = crear_usuario(
        Rol.CLIENTE, nombre_usuario="cliente_saldo_negativo", email="negativo@example.com"
    )
    db.add(
        Movimiento(
            cliente_id=cliente.id,
            tipo="compra",
            valor=-500_000,
            saldo_resultante=-1,
            referencia="ABC123",
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()


def test_el_signo_del_valor_corresponde_al_tipo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-48: recargas y reembolsos son positivos; las compras, negativas."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_signo", email="signo@example.com")
    db.add(
        Movimiento(
            cliente_id=cliente.id,
            tipo="recarga",
            valor=-500_000,
            saldo_resultante=0,
            referencia="**** 4242",
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()
