"""Recargas del monedero por HTTP (HU-30, RF-47)."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.apoyo import (
    MASTERCARD,
    RUTA_MONEDERO,
    RUTA_MOVIMIENTOS,
    RUTA_RECARGAS,
    crear_cliente,
    entrar,
    error_de,
    registrar_tarjeta,
)
from app.modules.monedero.tests.fabricas import crear_tarjeta


def test_hu30_una_recarga_suma_el_valor_y_registra_el_movimiento(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-30, RF-47: $ 500.000 aumentan el saldo exactamente en $ 500.000 y quedan en un
    movimiento `recarga` con la referencia de la tarjeta y su saldo resultante."""
    cliente = crear_cliente(db, crear_usuario, "recarga_exitosa")
    cliente_http = entrar(client, cliente)
    tarjeta = registrar_tarjeta(cliente_http, numero=MASTERCARD)

    respuesta = cliente_http.post(
        RUTA_RECARGAS, json={"tarjeta_id": tarjeta["id"], "valor": 500_000}
    )

    assert respuesta.status_code == 201
    movimiento = respuesta.json()
    assert movimiento["tipo"] == "recarga"
    assert movimiento["valor"] == 500_000
    assert movimiento["saldo_resultante"] == 500_000
    assert movimiento["referencia"] == "**** 4444"
    assert movimiento["creado_en"]

    assert cliente_http.get(RUTA_MONEDERO).json() == {"saldo": 500_000}
    listado = cliente_http.get(RUTA_MOVIMIENTOS).json()
    assert listado["total"] == 1
    assert listado["items"] == [movimiento]

    guardado = db.scalars(select(Movimiento)).one()
    assert guardado.cliente_id == cliente.id
    assert guardado.saldo_resultante == 500_000


def test_hu30_dos_recargas_acumulan_el_saldo(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-30, RF-48: cada recarga parte del saldo anterior y el movimiento lo refleja."""
    cliente_http = entrar(client, crear_cliente(db, crear_usuario, "recarga_doble"))
    tarjeta = registrar_tarjeta(cliente_http)

    primera = cliente_http.post(RUTA_RECARGAS, json={"tarjeta_id": tarjeta["id"], "valor": 500_000})
    segunda = cliente_http.post(RUTA_RECARGAS, json={"tarjeta_id": tarjeta["id"], "valor": 250_000})

    assert primera.json()["saldo_resultante"] == 500_000
    assert segunda.json()["saldo_resultante"] == 750_000
    assert cliente_http.get(RUTA_MONEDERO).json() == {"saldo": 750_000}


def test_hu30_rechaza_una_tarjeta_vencida(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-30: con una tarjeta vencida la recarga responde 422 `tarjeta_vencida` y no suma."""
    cliente = crear_cliente(db, crear_usuario, "recarga_vencida")
    cliente_http = entrar(client, cliente)
    tarjeta = crear_tarjeta(db, cliente.id, vencimiento=date(2025, 5, 1))

    respuesta = cliente_http.post(RUTA_RECARGAS, json={"tarjeta_id": tarjeta.id, "valor": 500_000})

    assert respuesta.status_code == 422
    error = error_de(respuesta)
    assert error["codigo"] == "tarjeta_vencida"
    assert error["campos"] == {
        "tarjeta_id": "La tarjeta está vencida. Elige otra o registra una nueva."
    }
    assert cliente_http.get(RUTA_MONEDERO).json() == {"saldo": 0}
    assert db.scalars(select(Movimiento)).all() == []


@pytest.mark.parametrize("valor", [0, -1])
def test_hu30_rechaza_un_valor_menor_o_igual_a_cero(
    valor: int, db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-30: un valor de 0 o negativo responde 422 `datos_invalidos` en `campos.valor`."""
    cliente_http = entrar(client, crear_cliente(db, crear_usuario, "recarga_valor"))
    tarjeta = registrar_tarjeta(cliente_http)

    respuesta = cliente_http.post(RUTA_RECARGAS, json={"tarjeta_id": tarjeta["id"], "valor": valor})

    assert respuesta.status_code == 422
    error = error_de(respuesta)
    assert error["codigo"] == "datos_invalidos"
    assert error["campos"]["valor"].startswith("Debe ser mayor que 0")
    assert cliente_http.get(RUTA_MONEDERO).json() == {"saldo": 0}
