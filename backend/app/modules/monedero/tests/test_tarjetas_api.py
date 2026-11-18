"""Tarjetas del monedero por HTTP (HU-28, HU-29, RNF-12)."""

import logging
import re
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.monedero.models import Movimiento, Tarjeta
from app.modules.monedero.tests.apoyo import (
    AMEX,
    DINERS,
    MASTERCARD,
    RUTA_MOVIMIENTOS,
    RUTA_RECARGAS,
    RUTA_TARJETAS,
    VISA,
    crear_cliente,
    entrar,
    error_de,
    numero_con_luhn,
    registrar_tarjeta,
    tarjeta_entrada,
)
from app.modules.monedero.tests.fabricas import crear_tarjeta

# ---------------------------------------------------------------------------
# HU-28 Registrar tarjeta
# ---------------------------------------------------------------------------


def test_hu28_registra_la_tarjeta_y_la_devuelve_enmascarada(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-28, RF-46, RNF-12: la tarjeta vuelve enmascarada y sin el número ni el CVV."""
    cliente = crear_cliente(db, crear_usuario, "tarjeta_api")

    respuesta = entrar(client, cliente).post(RUTA_TARJETAS, json=tarjeta_entrada())

    assert respuesta.status_code == 201
    tarjeta = respuesta.json()
    assert tarjeta["numero_enmascarado"] == "**** 4242"
    assert tarjeta["franquicia"] == "visa"
    assert tarjeta["tipo"] == "credito"
    assert tarjeta["titular"] == "LAURA GOMEZ RIOS"
    assert tarjeta["vencimiento"] == "08/28"
    assert tarjeta["vencida"] is False
    assert tarjeta["creada_en"]
    assert "numero" not in tarjeta
    assert "cvv" not in tarjeta
    assert VISA not in respuesta.text

    guardada = db.scalars(select(Tarjeta)).one()
    assert guardada.ultimos_4 == "4242"
    assert guardada.token
    assert guardada.cliente_id == cliente.id


def test_hu28_rechaza_un_numero_que_no_pasa_luhn(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-28, RF-46: un número que no pasa Luhn responde 422 `tarjeta_invalida`."""
    cliente = crear_cliente(db, crear_usuario, "tarjeta_luhn")

    respuesta = entrar(client, cliente).post(
        RUTA_TARJETAS, json=tarjeta_entrada(numero="4242424242424241")
    )

    assert respuesta.status_code == 422
    error = error_de(respuesta)
    assert error["codigo"] == "tarjeta_invalida"
    assert error["campos"] == {"numero": "El número no es válido. Revisa los dígitos."}


def test_hu28_rechaza_una_tarjeta_vencida(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-28, RF-46: un vencimiento anterior al mes actual responde 422 `tarjeta_vencida`."""
    cliente = crear_cliente(db, crear_usuario, "tarjeta_vencida_api")

    respuesta = entrar(client, cliente).post(
        RUTA_TARJETAS, json=tarjeta_entrada(vencimiento="05/26")
    )

    assert respuesta.status_code == 422
    error = error_de(respuesta)
    assert error["codigo"] == "tarjeta_vencida"
    assert error["campos"] == {"vencimiento": "La tarjeta está vencida."}
    assert db.scalars(select(Tarjeta)).all() == []


@pytest.mark.parametrize(
    ("numero", "franquicia"),
    [
        (VISA, "visa"),
        (MASTERCARD, "mastercard"),
        (AMEX, "amex"),
        (DINERS, "diners"),
        ("6011111111111117", "otra"),
    ],
)
def test_hu28_deduce_la_franquicia_del_numero(
    numero: str,
    franquicia: str,
    db: Session,
    client: TestClient,
    crear_usuario: Callable[..., Any],
) -> None:
    """HU-28: la franquicia la deduce el backend a partir del número."""
    cliente = crear_cliente(db, crear_usuario, f"tarjeta_franquicia_{franquicia}")

    tarjeta = registrar_tarjeta(entrar(client, cliente), numero=numero)

    assert tarjeta["franquicia"] == franquicia
    assert tarjeta["numero_enmascarado"] == f"**** {numero[-4:]}"


def test_hu28_veinte_tarjetas_no_dejan_el_numero_ni_el_cvv(
    db: Session,
    client: TestClient,
    crear_usuario: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """HU-28, RNF-12: tras registrar 20 tarjetas, ni la base ni los logs guardan el número
    completo ni el CVV; solo los últimos 4 dígitos y el token simulado."""
    cliente = crear_cliente(db, crear_usuario, "tarjeta_rnf12")
    entrar(client, cliente)
    caplog.set_level(logging.DEBUG)

    numeros: list[str] = []
    cvvs: list[str] = []
    for indice in range(20):
        numero = numero_con_luhn(f"4242424242{indice:04d}")
        cvv = f"9{indice:03d}"
        numeros.append(numero)
        cvvs.append(cvv)
        respuesta = client.post(RUTA_TARJETAS, json=tarjeta_entrada(numero=numero, cvv=cvv))
        assert respuesta.status_code == 201, respuesta.text

    assert not re.search(r"\d{13,19}", _texto_de_la_base(db))
    texto_de_la_base = _texto_de_la_base(db)
    for numero in numeros:
        assert numero not in texto_de_la_base
        assert numero not in caplog.text
    for cvv in cvvs:
        assert cvv not in caplog.text


def _texto_de_la_base(db: Session) -> str:
    """Las columnas de texto de tarjetas y movimientos, para buscar números completos.

    El `token` simulado queda fuera: es hexadecimal aleatorio y puede contener una seguidilla
    de dígitos sin ser el número de una tarjeta.
    """
    valores: list[str] = []
    for tarjeta in db.scalars(select(Tarjeta)).all():
        valores += [tarjeta.tipo, tarjeta.franquicia, tarjeta.titular, tarjeta.ultimos_4]
    for movimiento in db.scalars(select(Movimiento)).all():
        valores += [movimiento.tipo, movimiento.referencia]
    return "\n".join(valores)


# ---------------------------------------------------------------------------
# HU-29 Eliminar tarjeta
# ---------------------------------------------------------------------------


def test_hu29_la_tarjeta_eliminada_ya_no_aparece_ni_sirve_para_recargar(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-29: el borrado es lógico: deja de listarse y de servir para recargar."""
    cliente = crear_cliente(db, crear_usuario, "tarjeta_eliminada")
    cliente_http = entrar(client, cliente)
    tarjeta = registrar_tarjeta(cliente_http)

    respuesta = cliente_http.delete(f"{RUTA_TARJETAS}/{tarjeta['id']}")

    assert respuesta.status_code == 204
    assert cliente_http.get(RUTA_TARJETAS).json() == []
    recarga = cliente_http.post(RUTA_RECARGAS, json={"tarjeta_id": tarjeta["id"], "valor": 500_000})
    assert recarga.status_code == 404
    assert error_de(recarga)["codigo"] == "no_encontrado"
    assert (
        error_de(cliente_http.delete(f"{RUTA_TARJETAS}/{tarjeta['id']}"))["mensaje"]
        == "La tarjeta no existe."
    )


def test_hu29_las_recargas_hechas_con_ella_conservan_su_referencia(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-29: los movimientos históricos hechos con la tarjeta conservan `**** 1234`."""
    cliente = crear_cliente(db, crear_usuario, "tarjeta_historica")
    cliente_http = entrar(client, cliente)
    tarjeta = registrar_tarjeta(cliente_http, numero=MASTERCARD)
    cliente_http.post(RUTA_RECARGAS, json={"tarjeta_id": tarjeta["id"], "valor": 500_000})

    cliente_http.delete(f"{RUTA_TARJETAS}/{tarjeta['id']}")

    movimientos = cliente_http.get(RUTA_MOVIMIENTOS).json()
    assert movimientos["total"] == 1
    assert movimientos["items"][0]["referencia"] == "**** 4444"


def test_hu29_lista_las_tarjetas_recientes_primero_e_incluye_vencidas(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-29: el listado va de la más reciente a la más antigua e incluye las vencidas."""
    cliente = crear_cliente(db, crear_usuario, "tarjeta_listado")
    cliente_http = entrar(client, cliente)
    primera = registrar_tarjeta(cliente_http)
    segunda = registrar_tarjeta(cliente_http, numero=MASTERCARD)
    vencida = crear_tarjeta(db, cliente.id, ultimos_4="1111", vencimiento=date(2025, 5, 1))

    tarjetas = cliente_http.get(RUTA_TARJETAS).json()

    assert [tarjeta["id"] for tarjeta in tarjetas] == [vencida.id, segunda["id"], primera["id"]]
    assert tarjetas[0]["vencida"] is True
    assert tarjetas[0]["vencimiento"] == "05/25"
    assert tarjetas[1]["vencida"] is False
