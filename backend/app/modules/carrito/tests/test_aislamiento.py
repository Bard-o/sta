"""Aislamiento entre clientes del carrito (HU-22, HU-23)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.carrito.tests.apoyo import (
    RUTA_CARRITO,
    RUTA_SELECCIONES,
    agregar,
    crear_cliente,
    entrar,
    error_de,
    tramo,
)
from app.modules.vuelos.tests.fabricas import crear_vuelo

SALIDA = datetime(2027, 4, 15, 11, 0, tzinfo=UTC)


def test_hu23_un_cliente_no_ve_ni_modifica_el_carrito_de_otro(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: un id ajeno responde `404 no_encontrado`, igual que uno que no existe.

    El carrito de la dueña queda intacto.
    """
    duena = crear_cliente(db, crear_usuario, "duena_del_carrito")
    otro = crear_cliente(db, crear_usuario, "otro_cliente_del_carrito")
    vuelo = crear_vuelo(db, salida=SALIDA)

    cliente_http = entrar(client, duena)
    creada = agregar(cliente_http, [tramo(vuelo.id)], viajeros=2)
    assert creada.status_code == 201, creada.text
    seleccion_id = creada.json()["id"]

    cliente_http = entrar(client, otro)
    assert cliente_http.get(RUTA_CARRITO).json() == {
        "selecciones": [],
        "cantidad": 0,
        "total": 0,
    }
    modificar = cliente_http.patch(f"{RUTA_SELECCIONES}/{seleccion_id}", json={"viajeros": 1})
    assert modificar.status_code == 404
    assert error_de(modificar)["codigo"] == "no_encontrado"
    assert error_de(modificar)["mensaje"] == "La selección no existe."
    quitar = cliente_http.delete(f"{RUTA_SELECCIONES}/{seleccion_id}")
    assert quitar.status_code == 404
    assert error_de(quitar)["mensaje"] == "La selección no existe."
    assert cliente_http.delete(f"{RUTA_SELECCIONES}/9999").status_code == 404

    cliente_http = entrar(client, duena)
    carrito = cliente_http.get(RUTA_CARRITO).json()
    assert [seleccion["id"] for seleccion in carrito["selecciones"]] == [seleccion_id]
    assert carrito["selecciones"][0]["viajeros"] == 2
