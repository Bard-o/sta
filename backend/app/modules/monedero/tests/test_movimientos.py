"""Saldo y movimientos del monedero por HTTP (HU-31, RF-48)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.monedero.tests.apoyo import (
    RUTA_MONEDERO,
    RUTA_MOVIMIENTOS,
    crear_cliente,
    entrar,
    error_de,
)
from app.modules.monedero.tests.fabricas import crear_movimiento

_CLAVES_DEL_MOVIMIENTO = {"id", "tipo", "valor", "saldo_resultante", "referencia", "creado_en"}


def test_hu31_lista_los_movimientos_del_mas_reciente_al_mas_antiguo(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31: del más reciente al más antiguo, con fecha, tipo, referencia, valor y saldo
    resultante (RF-48)."""
    cliente = crear_cliente(db, crear_usuario, "movimientos_orden")
    recarga = crear_movimiento(
        db,
        cliente.id,
        tipo="recarga",
        valor=500_000,
        saldo_resultante=500_000,
        referencia="**** 4242",
        creado_en=datetime(2026, 11, 10, 15, 0, tzinfo=UTC),
    )
    compra = crear_movimiento(
        db,
        cliente.id,
        tipo="compra",
        valor=-200_000,
        saldo_resultante=300_000,
        referencia="K7Q2MX",
        creado_en=datetime(2026, 11, 10, 16, 0, tzinfo=UTC),
    )
    reembolso = crear_movimiento(
        db,
        cliente.id,
        tipo="reembolso",
        valor=50_000,
        saldo_resultante=350_000,
        referencia="Q8W2RT",
        creado_en=datetime(2026, 11, 10, 17, 0, tzinfo=UTC),
    )

    respuesta = entrar(client, cliente).get(RUTA_MOVIMIENTOS)

    assert respuesta.status_code == 200
    pagina = respuesta.json()
    assert pagina["total"] == 3
    assert [item["id"] for item in pagina["items"]] == [reembolso.id, compra.id, recarga.id]
    assert {*pagina["items"][0]} == _CLAVES_DEL_MOVIMIENTO
    assert pagina["items"][0] == {
        "id": reembolso.id,
        "tipo": "reembolso",
        "valor": 50_000,
        "saldo_resultante": 350_000,
        "referencia": "Q8W2RT",
        "creado_en": "2026-11-10T17:00:00Z",
    }
    assert pagina["items"][1]["valor"] == -200_000


def test_hu31_filtra_por_tipo(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31: filtrar por «recarga» muestra solo las recargas."""
    cliente = crear_cliente(db, crear_usuario, "movimientos_tipo")
    crear_movimiento(db, cliente.id, tipo="recarga", valor=500_000, saldo_resultante=500_000)
    crear_movimiento(db, cliente.id, tipo="compra", valor=-200_000, saldo_resultante=300_000)
    crear_movimiento(db, cliente.id, tipo="reembolso", valor=50_000, saldo_resultante=350_000)

    pagina = entrar(client, cliente).get(f"{RUTA_MOVIMIENTOS}?tipo=recarga").json()

    assert pagina["total"] == 1
    assert {item["tipo"] for item in pagina["items"]} == {"recarga"}


def test_hu31_filtra_por_fecha_en_hora_de_colombia(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31: `desde` y `hasta` son fechas del movimiento en hora de Colombia; incluyen el día
    completo, así que un movimiento de las 23:30 locales pertenece a ese día."""
    cliente = crear_cliente(db, crear_usuario, "movimientos_fecha")
    # 2026-11-10T04:30Z es el 2026-11-09 a las 23:30 en Bogotá.
    noche = crear_movimiento(
        db,
        cliente.id,
        creado_en=datetime(2026, 11, 10, 4, 30, tzinfo=UTC),
        saldo_resultante=500_000,
    )
    # 2026-11-10T15:00Z es el 2026-11-10 a las 10:00 en Bogotá.
    dia = crear_movimiento(
        db,
        cliente.id,
        creado_en=datetime(2026, 11, 10, 15, 0, tzinfo=UTC),
        saldo_resultante=500_000,
    )
    cliente_http = entrar(client, cliente)

    del_nueve = cliente_http.get(f"{RUTA_MOVIMIENTOS}?desde=2026-11-09&hasta=2026-11-09").json()
    del_diez = cliente_http.get(f"{RUTA_MOVIMIENTOS}?desde=2026-11-10&hasta=2026-11-10").json()

    assert [item["id"] for item in del_nueve["items"]] == [noche.id]
    assert [item["id"] for item in del_diez["items"]] == [dia.id]
    assert cliente_http.get(f"{RUTA_MOVIMIENTOS}?desde=2026-11-09").json()["total"] == 2
    assert cliente_http.get(f"{RUTA_MOVIMIENTOS}?desde=2026-11-11").json()["total"] == 0


def test_hu31_un_rango_invalido_responde_422(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31: `hasta` anterior a `desde` responde 422 `rango_invalido` en `campos.hasta`."""
    cliente_http = entrar(client, crear_cliente(db, crear_usuario, "movimientos_rango"))

    respuesta = cliente_http.get(f"{RUTA_MOVIMIENTOS}?desde=2026-11-10&hasta=2026-11-09")

    assert respuesta.status_code == 422
    error = error_de(respuesta)
    assert error["codigo"] == "rango_invalido"
    assert error["campos"] == {"hasta": "La fecha final no puede ser anterior a la inicial."}


def test_hu31_pagina_los_movimientos(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31: `pagina` y `por_pagina` recorren los movimientos; `total` cuenta los filtrados."""
    cliente = crear_cliente(db, crear_usuario, "movimientos_pagina")
    for indice in range(3):
        crear_movimiento(
            db,
            cliente.id,
            creado_en=datetime(2026, 11, 10, 15, indice, tzinfo=UTC),
            saldo_resultante=500_000,
        )
    cliente_http = entrar(client, cliente)

    primera = cliente_http.get(f"{RUTA_MOVIMIENTOS}?pagina=1&por_pagina=2").json()
    segunda = cliente_http.get(f"{RUTA_MOVIMIENTOS}?pagina=2&por_pagina=2").json()

    assert primera["total"] == 3
    assert primera["pagina"] == 1
    assert primera["por_pagina"] == 2
    assert len(primera["items"]) == 2
    assert len(segunda["items"]) == 1
    assert {*primera["items"][0]} == _CLAVES_DEL_MOVIMIENTO


def test_hu31_un_cliente_sin_movimientos_tiene_saldo_cero(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31: sin movimientos el saldo es $ 0 y el listado llega vacío (RF-48)."""
    cliente_http = entrar(client, crear_cliente(db, crear_usuario, "movimientos_vacio"))

    assert cliente_http.get(RUTA_MONEDERO).json() == {"saldo": 0}
    assert cliente_http.get(RUTA_MOVIMIENTOS).json() == {
        "items": [],
        "total": 0,
        "pagina": 1,
        "por_pagina": 20,
    }


def test_hu31_el_saldo_es_la_suma_de_los_movimientos(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31, RF-48: el saldo mostrado es la suma de todos los movimientos del cliente."""
    cliente = crear_cliente(db, crear_usuario, "movimientos_suma")
    crear_movimiento(db, cliente.id, tipo="recarga", valor=500_000, saldo_resultante=500_000)
    crear_movimiento(db, cliente.id, tipo="compra", valor=-200_000, saldo_resultante=300_000)
    crear_movimiento(db, cliente.id, tipo="reembolso", valor=50_000, saldo_resultante=350_000)

    cliente_http = entrar(client, cliente)
    saldo = cliente_http.get(RUTA_MONEDERO).json()["saldo"]
    items = cliente_http.get(RUTA_MOVIMIENTOS).json()["items"]

    assert saldo == 350_000
    assert sum(item["valor"] for item in items) == saldo
    # El movimiento más reciente es el que deja el saldo actual.
    assert items[0]["saldo_resultante"] == saldo
