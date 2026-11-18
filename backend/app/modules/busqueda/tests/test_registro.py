"""RF-29, RF-60: las búsquedas de los clientes se registran para la recomendación."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.busqueda.models import Busqueda
from app.modules.vuelos.tests.fabricas import crear_vuelo

IDA = datetime(2027, 4, 15, 15, 0, tzinfo=UTC)
REGRESO = datetime(2027, 4, 22, 15, 0, tzinfo=UTC)


def _iniciar_sesion(client: TestClient, usuario: Any) -> None:
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200, respuesta.text


def test_hu20_el_visitante_no_registra_la_busqueda(client: TestClient, db: Session) -> None:
    """HU-20 · una búsqueda sin sesión no crea registros asociados a ningún usuario."""
    crear_vuelo(db, origen="PEI", salida=IDA)

    respuesta = client.get("/api/v1/busqueda/vuelos", params={"origen": "PEI"})

    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 1
    assert db.scalars(select(Busqueda)).all() == []


def test_hu20_el_cliente_registra_criterios_hora_y_cantidad_de_resultados(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
) -> None:
    """HU-20 · la búsqueda de un cliente autenticado sí se registra, con sus criterios, la
    hora y la cantidad de resultados (RF-29, RF-60)."""
    crear_vuelo(db, origen="PEI", salida=IDA)
    usuario = crear_usuario(Rol.CLIENTE)
    _iniciar_sesion(client, usuario)

    respuesta = client.get(
        "/api/v1/busqueda/vuelos",
        params={
            "origen": "PEI",
            "precio_min": 200000,
            "precio_max": 400000,
            "fecha_desde": "2027-04-15",
            "clase": "economica",
            "orden": "fecha",
        },
    )

    assert respuesta.status_code == 200
    busqueda = db.scalars(select(Busqueda)).one()
    assert busqueda.criterios == {
        "origen": "PEI",
        "fecha_desde": "2027-04-15",
        "precio_min": 200000,
        "precio_max": 400000,
        "clase": "economica",
        "orden": "fecha",
    }
    assert busqueda.total == respuesta.json()["total"] == 1
    assert busqueda.registrada_en.utcoffset() is not None


def test_hu20_solo_la_primera_pagina_se_registra(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
) -> None:
    """HU-20 · no se registran las páginas siguientes de la misma búsqueda."""
    crear_vuelo(db, origen="PEI", salida=IDA)
    _iniciar_sesion(client, crear_usuario(Rol.CLIENTE))

    for pagina in (1, 2):
        respuesta = client.get(
            "/api/v1/busqueda/vuelos", params={"origen": "PEI", "pagina": pagina}
        )
        assert respuesta.status_code == 200

    assert len(db.scalars(select(Busqueda)).all()) == 1


@pytest.mark.parametrize("rol", [Rol.ADMIN, Rol.ROOT], ids=lambda r: r.value)
def test_rf29_no_se_registran_las_busquedas_de_admin_ni_de_root(
    rol: Rol,
    client_como: Callable[[Rol], TestClient],
    db: Session,
) -> None:
    """RF-29 · solo los clientes se registran; administrador y root no."""
    crear_vuelo(db, origen="PEI", salida=IDA)

    respuesta = client_como(rol).get("/api/v1/busqueda/vuelos", params={"origen": "PEI"})

    assert respuesta.status_code == 200
    assert db.scalars(select(Busqueda)).all() == []


def test_hu21_el_regreso_del_cliente_se_registra_con_la_ida(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
) -> None:
    """HU-21 · el regreso se registra con el vuelo de ida, la ciudad y la fecha."""
    ida = crear_vuelo(db, origen="PEI", destino="JFK", salida=IDA, duracion_minutos=330)
    crear_vuelo(db, origen="JFK", destino="CTG", salida=REGRESO)
    _iniciar_sesion(client, crear_usuario(Rol.CLIENTE))

    respuesta = client.get(
        "/api/v1/busqueda/regresos",
        params={"vuelo_ida_id": ida.id, "destino": "CTG", "fecha": "2027-04-22"},
    )

    assert respuesta.status_code == 200
    busqueda = db.scalars(select(Busqueda)).one()
    assert busqueda.criterios == {
        "vuelo_ida_id": ida.id,
        "destino": "CTG",
        "fecha": "2027-04-22",
        "orden": "precio",
    }
    assert busqueda.total == 1


def test_una_busqueda_invalida_no_se_registra(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
) -> None:
    """RF-29 · una búsqueda rechazada no deja registro."""
    _iniciar_sesion(client, crear_usuario(Rol.CLIENTE))

    respuesta = client.get(
        "/api/v1/busqueda/vuelos", params={"precio_min": 400000, "precio_max": 200000}
    )

    assert respuesta.status_code == 422
    assert db.scalars(select(Busqueda)).all() == []
