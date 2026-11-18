"""Búsqueda pública de vuelos (HU-20, HU-21, RF-27, RF-28)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.vuelos.tests.fabricas import crear_promocion_bd, crear_vuelo

IDA = datetime(2027, 4, 15, 15, 0, tzinfo=UTC)
MENSAJE_RANGOS = "Revisa los rangos marcados."


def _error(respuesta: Any) -> dict[str, Any]:
    return respuesta.json()["error"]


@pytest.mark.parametrize(
    ("parametros", "campo"),
    [
        ({"precio_min": 400000, "precio_max": 200000}, "precio_max"),
        ({"fecha_desde": "2027-04-20", "fecha_hasta": "2027-04-15"}, "fecha_hasta"),
        ({"hora_desde": "18:00", "hora_hasta": "06:00"}, "hora_hasta"),
        ({"duracion_min": 120, "duracion_max": 60}, "duracion_max"),
    ],
    ids=["precio", "fecha", "hora", "duracion"],
)
def test_hu20_un_rango_invalido_responde_rango_invalido_con_el_campo(
    client: TestClient, parametros: dict[str, object], campo: str
) -> None:
    """HU-20 · un rango inválido (mínimo mayor que el máximo, o fecha final anterior a la
    inicial) responde el error del contrato con el campo que falla."""
    respuesta = client.get("/api/v1/busqueda/vuelos", params=parametros)

    assert respuesta.status_code == 422
    error = _error(respuesta)
    assert error["codigo"] == "rango_invalido"
    assert error["mensaje"] == MENSAJE_RANGOS
    assert set(error["campos"]) == {campo}


def test_hu20_varios_rangos_invalidos_vienen_todos(client: TestClient) -> None:
    """HU-20 · si fallan varios rangos, `campos` trae todos los extremos que fallan."""
    respuesta = client.get(
        "/api/v1/busqueda/vuelos",
        params={"precio_min": 400000, "precio_max": 200000}
        | {"duracion_min": 120, "duracion_max": 60},
    )

    assert respuesta.status_code == 422
    assert set(_error(respuesta)["campos"]) == {"precio_max", "duracion_max"}


@pytest.mark.parametrize(
    "parametros",
    [{"origen": "pe"}, {"fecha_desde": "2027-02-30"}, {"orden": "barato"}],
    ids=["ciudad", "fecha", "orden"],
)
def test_hu20_un_formato_invalido_responde_datos_invalidos(
    client: TestClient, parametros: dict[str, object]
) -> None:
    """HU-20 · un formato inválido responde `datos_invalidos` con el campo que falla."""
    respuesta = client.get("/api/v1/busqueda/vuelos", params=parametros)

    assert respuesta.status_code == 422
    error = _error(respuesta)
    assert error["codigo"] == "datos_invalidos"
    assert error["campos"]


def test_hu20_el_resultado_tiene_el_formato_del_contrato(client: TestClient, db: Session) -> None:
    """HU-20 · cada resultado trae ruta, horas, precio vigente con promoción y disponibilidad."""
    vuelo = crear_vuelo(db, origen="PEI", destino="BOG", salida=IDA)
    crear_promocion_bd(db, vuelo, porcentaje=20)

    respuesta = client.get("/api/v1/busqueda/vuelos", params={"origen": "PEI"})

    assert respuesta.status_code == 200
    item = respuesta.json()["items"][0]
    assert item["id"] == vuelo.id
    assert item["codigo"] == vuelo.codigo
    assert item["origen"] == {
        "codigo": "PEI",
        "nombre": "Pereira",
        "zona_horaria": "America/Bogota",
    }
    assert item["destino"]["codigo"] == "BOG"
    assert item["duracion_minutos"] == 50
    assert item["economica"] == {
        "precio_base": 280000,
        "precio_vigente": 224000,
        "promocion": {"porcentaje": 20, "fin": item["economica"]["promocion"]["fin"]},
        "disponibles": 125,
        "agotada": False,
    }
    assert item["primera"]["precio_base"] == 750000
    assert item["primera"]["promocion"] is None
    assert item["agotado"] is False


def test_hu21_no_ofrece_regresos_que_salen_antes_de_la_llegada(
    client: TestClient, db: Session
) -> None:
    """HU-21 · si la ida llega el 15/04 a las 16:30 (Nueva York), no se ofrece ningún regreso
    que salga antes de esa hora (RF-28)."""
    ida = crear_vuelo(db, origen="PEI", destino="JFK", salida=IDA, duracion_minutos=330)
    crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        salida=datetime(2027, 4, 15, 18, 0, tzinfo=UTC),
    )
    despues = crear_vuelo(
        db, origen="JFK", destino="CTG", salida=datetime(2027, 4, 15, 22, 0, tzinfo=UTC)
    )

    respuesta = client.get(
        "/api/v1/busqueda/regresos",
        params={"vuelo_ida_id": ida.id, "destino": "CTG", "fecha": "2027-04-15"},
    )

    assert respuesta.status_code == 200
    assert [item["id"] for item in respuesta.json()["items"]] == [despues.id]


def test_hu21_una_fecha_de_regreso_anterior_a_la_ida_se_rechaza(
    client: TestClient, db: Session
) -> None:
    """HU-21 · una fecha de regreso anterior a la de ida es rechazada."""
    ida = crear_vuelo(db, origen="PEI", destino="JFK", salida=IDA, duracion_minutos=330)

    respuesta = client.get(
        "/api/v1/busqueda/regresos",
        params={"vuelo_ida_id": ida.id, "destino": "CTG", "fecha": "2027-04-14"},
    )

    assert respuesta.status_code == 422
    error = _error(respuesta)
    assert error["codigo"] == "rango_invalido"
    assert error["campos"] == {"fecha": "La fecha de regreso no puede ser anterior a la de ida."}


def test_hu21_una_ida_inexistente_responde_no_encontrado(client: TestClient) -> None:
    """HU-21 · si la ida no existe o ya no está a la venta, responde `no_encontrado`."""
    respuesta = client.get(
        "/api/v1/busqueda/regresos",
        params={"vuelo_ida_id": 999999, "destino": "CTG", "fecha": "2027-04-22"},
    )

    assert respuesta.status_code == 404
    error = _error(respuesta)
    assert error["codigo"] == "no_encontrado"
    assert error["mensaje"] == "El vuelo de ida no existe o ya no está a la venta."
