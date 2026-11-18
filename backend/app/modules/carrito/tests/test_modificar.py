"""HU-23: modificar, quitar y vaciar el carrito (RF-30, RF-32, RF-33)."""

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
from app.modules.carrito.tests.fabricas import crear_seleccion
from app.modules.reservas.tests.fabricas import crear_compra
from app.modules.vuelos.tests.fabricas import crear_promocion_bd, crear_vuelo

SALIDA = datetime(2027, 4, 15, 11, 0, tzinfo=UTC)


def test_hu23_cambiar_la_cantidad_revalida_el_limite(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23 · RF-32: con 4 tiquetes activos, pasar a 2 viajeros supera el máximo de 5."""
    cliente = crear_cliente(db, crear_usuario, "cliente_cambia_cantidad")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_compra(db, cliente.id, vuelo, cantidad=4)
    seleccion = crear_seleccion(db, cliente.id, [vuelo])
    cliente_http = entrar(client, cliente)
    ruta = f"{RUTA_SELECCIONES}/{seleccion.id}"

    rechazo = cliente_http.patch(ruta, json={"viajeros": 2})
    assert rechazo.status_code == 409
    assert error_de(rechazo)["codigo"] == "limite_tiquetes"

    aceptado = cliente_http.patch(ruta, json={"viajeros": 1})
    assert aceptado.status_code == 200, aceptado.text
    assert aceptado.json()["viajeros"] == 1


def test_hu23_cambiar_la_clase_revalida_el_cupo(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23 · RF-33: primera con una sola silla no admite dos viajeros."""
    cliente = crear_cliente(db, crear_usuario, "cliente_cambia_clase")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_primera=1)
    seleccion = crear_seleccion(db, cliente.id, [vuelo])
    cliente_http = entrar(client, cliente)
    ruta = f"{RUTA_SELECCIONES}/{seleccion.id}"

    rechazo = cliente_http.patch(ruta, json={"clases": ["primera"], "viajeros": 2})
    assert rechazo.status_code == 409
    assert error_de(rechazo)["codigo"] == "clase_agotada"

    aceptado = cliente_http.patch(ruta, json={"clases": ["primera"], "viajeros": 1})
    assert aceptado.status_code == 200, aceptado.text
    assert aceptado.json()["tramos"][0]["clase"] == "primera"
    assert aceptado.json()["tramos"][0]["precio_al_agregar"] == 750_000


def test_hu23_quitar_una_seleccion_y_vaciar_se_refleja_de_inmediato(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: quitar una selección o vaciar el carrito se ve en la siguiente lectura.

    Vaciar un carrito vacío también responde 204.
    """
    cliente = crear_cliente(db, crear_usuario, "cliente_quita")
    uno = crear_vuelo(db, salida=SALIDA)
    dos = crear_vuelo(
        db, origen="PEI", destino="MDE", salida=datetime(2027, 4, 15, 8, 0, tzinfo=UTC)
    )
    primera = crear_seleccion(db, cliente.id, [uno])
    crear_seleccion(db, cliente.id, [dos])
    cliente_http = entrar(client, cliente)

    assert cliente_http.delete(f"{RUTA_SELECCIONES}/{primera.id}").status_code == 204
    assert cliente_http.get(RUTA_CARRITO).json()["cantidad"] == 1

    assert cliente_http.delete(RUTA_CARRITO).status_code == 204
    assert cliente_http.get(RUTA_CARRITO).json()["selecciones"] == []
    assert cliente_http.delete(RUTA_CARRITO).status_code == 204


def test_hu23_un_cuerpo_vacio_no_cambia_nada(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: `PATCH` con `{}` no cambia viajeros ni renueva el precio de referencia."""
    cliente = crear_cliente(db, crear_usuario, "cliente_vacio")
    vuelo = crear_vuelo(db, salida=SALIDA)
    cliente_http = entrar(client, cliente)
    creada = agregar(cliente_http, [tramo(vuelo.id)], viajeros=2)
    crear_promocion_bd(db, vuelo, porcentaje=20)

    respuesta = cliente_http.patch(f"{RUTA_SELECCIONES}/{creada.json()['id']}", json={})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["viajeros"] == 2
    assert respuesta.json()["tramos"][0]["clase"] == "economica"
    assert respuesta.json()["tramos"][0]["precio_al_agregar"] == 280_000


def test_hu23_modificar_renueva_el_precio_al_agregar(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: al modificar, el precio de referencia queda en el vigente y se borra el aviso."""
    cliente = crear_cliente(db, crear_usuario, "cliente_renueva")
    vuelo = crear_vuelo(db, salida=SALIDA)
    seleccion = crear_seleccion(db, cliente.id, [vuelo])
    crear_promocion_bd(db, vuelo, porcentaje=20)
    cliente_http = entrar(client, cliente)

    respuesta = cliente_http.patch(f"{RUTA_SELECCIONES}/{seleccion.id}", json={"viajeros": 2})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tramos"][0]["precio_al_agregar"] == 224_000
    assert respuesta.json()["avisos"] == []


def test_hu23_las_clases_deben_traer_una_por_tramo(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: un número distinto de clases responde `datos_invalidos` en `campos.clases`."""
    cliente = crear_cliente(db, crear_usuario, "cliente_clases")
    vuelo = crear_vuelo(db, salida=SALIDA)
    seleccion = crear_seleccion(db, cliente.id, [vuelo])
    cliente_http = entrar(client, cliente)

    respuesta = cliente_http.patch(
        f"{RUTA_SELECCIONES}/{seleccion.id}",
        json={"clases": ["economica", "primera"]},
    )

    assert respuesta.status_code == 422
    assert error_de(respuesta)["codigo"] == "datos_invalidos"
    assert error_de(respuesta)["campos"]["clases"] == "Debe traer una clase por cada tramo."
