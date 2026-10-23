"""Contrato HTTP del detalle público del vuelo (HU-19)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.reservas.service import OcupacionVuelo
from app.modules.vuelos.tests.fabricas import (
    crear_promocion_bd,
    crear_vuelo,
    simular_ocupacion,
)

SALIDA = datetime(2099, 1, 15, 10, 0, tzinfo=UTC)
PRECIO_ECONOMICA = 280_000
PRECIO_PRIMERA = 750_000


def ruta(vuelo_id: int) -> str:
    return f"/api/v1/vuelos/{vuelo_id}"


def ahora() -> datetime:
    return datetime.now(UTC)


def fecha(valor: str) -> datetime:
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def test_detalle_publico_responde_sin_sesion_con_el_contrato(
    client: TestClient, db: Session
) -> None:
    """HU-19 · criterio 1: el detalle del vuelo abre sin sesión, desde una noticia o el
    carrusel, con la forma completa de `VueloDetalle`."""
    vuelo = crear_vuelo(db, salida=SALIDA)

    respuesta = client.get(ruta(vuelo.id))

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert set(datos) == {
        "id",
        "codigo",
        "tipo",
        "origen",
        "destino",
        "salida",
        "llegada",
        "duracion_minutos",
        "precio_economica",
        "precio_primera",
        "capacidad",
        "estado",
        "economica",
        "primera",
    }
    assert datos["id"] == vuelo.id
    assert datos["codigo"] == vuelo.codigo
    assert datos["estado"] == "programado"
    assert datos["origen"] == {
        "codigo": "PEI",
        "nombre": "Pereira",
        "zona_horaria": "America/Bogota",
    }
    assert datos["destino"] == {
        "codigo": "BOG",
        "nombre": "Bogotá",
        "zona_horaria": "America/Bogota",
    }
    assert datos["capacidad"] == {"primera": 25, "economica": 125, "total": 150}
    for clase in ("economica", "primera"):
        assert set(datos[clase]) == {
            "precio_base",
            "precio_vigente",
            "promocion",
            "disponibles",
            "agotada",
        }


def test_detalle_sin_promocion_devuelve_el_precio_base(client: TestClient, db: Session) -> None:
    """HU-19 · criterio 2: sin promoción vigente, cada clase trae su precio base y
    `promocion` en null."""
    vuelo = crear_vuelo(db, salida=SALIDA)

    datos = client.get(ruta(vuelo.id)).json()

    assert datos["economica"]["precio_base"] == PRECIO_ECONOMICA
    assert datos["economica"]["precio_vigente"] == PRECIO_ECONOMICA
    assert datos["economica"]["promocion"] is None
    assert datos["primera"]["precio_base"] == PRECIO_PRIMERA
    assert datos["primera"]["precio_vigente"] == PRECIO_PRIMERA
    assert datos["primera"]["promocion"] is None


def test_detalle_con_promocion_vigente_devuelve_el_precio_con_descuento(
    client: TestClient, db: Session
) -> None:
    """HU-19 · criterio 2: con promoción vigente, `precio_vigente` lleva el descuento y
    `promocion` trae sus datos; la otra clase conserva su precio base."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    momento = ahora()
    promocion = crear_promocion_bd(
        db,
        vuelo,
        porcentaje=20,
        clases=["economica"],
        inicio=momento - timedelta(hours=1),
        fin=momento + timedelta(days=7),
    )

    datos = client.get(ruta(vuelo.id)).json()

    assert datos["economica"]["precio_base"] == PRECIO_ECONOMICA
    assert datos["economica"]["precio_vigente"] == 224_000
    promocion_datos = datos["economica"]["promocion"]
    assert set(promocion_datos) == {
        "id",
        "porcentaje",
        "clases",
        "inicio",
        "fin",
        "estado",
    }
    assert promocion_datos["id"] == promocion.id
    assert promocion_datos["porcentaje"] == 20
    assert promocion_datos["clases"] == ["economica"]
    assert promocion_datos["estado"] == "vigente"
    assert fecha(promocion_datos["inicio"]) == promocion.inicio
    assert fecha(promocion_datos["fin"]) == promocion.fin
    assert datos["primera"]["precio_vigente"] == PRECIO_PRIMERA
    assert datos["primera"]["promocion"] is None


def test_detalle_informa_disponibles_y_agotada_por_clase(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-19 · criterio 2: `disponibles` y `agotada` salen de la ocupación de cada clase."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_ocupacion(monkeypatch, {vuelo.id: OcupacionVuelo(vendidas_economica=125)})

    datos = client.get(ruta(vuelo.id)).json()

    assert datos["economica"]["disponibles"] == 0
    assert datos["economica"]["agotada"] is True
    assert datos["primera"]["disponibles"] == 25
    assert datos["primera"]["agotada"] is False


@pytest.mark.parametrize("estado", ["realizado", "cancelado"])
def test_detalle_responde_para_cualquier_estado_del_vuelo(
    client: TestClient, db: Session, estado: str
) -> None:
    """HU-19 · criterio 3: responde para cualquier `estado`; si el vuelo ya no está
    programado, el frontend avisa y no se ofrece ninguna promoción."""
    vuelo = crear_vuelo(db, salida=SALIDA, estado=estado)
    momento = ahora()
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=20,
        clases=["economica", "primera"],
        inicio=momento - timedelta(hours=1),
        fin=momento + timedelta(days=7),
    )

    respuesta = client.get(ruta(vuelo.id))

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["estado"] == estado
    for clase in ("economica", "primera"):
        assert datos[clase]["promocion"] is None
        assert datos[clase]["precio_vigente"] == datos[clase]["precio_base"]


def test_detalle_de_un_vuelo_programado_que_ya_salio_no_ofrece_promocion(
    client: TestClient, db: Session
) -> None:
    """HU-19 · criterio 3: un vuelo `programado` con la salida pasada responde, pero ya no
    está disponible para la venta y vuelve al precio base."""
    vuelo = crear_vuelo(db, salida=ahora() - timedelta(days=1))
    momento = ahora()
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=20,
        clases=["economica"],
        inicio=momento - timedelta(hours=1),
        fin=momento + timedelta(days=7),
    )

    datos = client.get(ruta(vuelo.id)).json()

    assert datos["estado"] == "programado"
    assert datos["economica"]["promocion"] is None
    assert datos["economica"]["precio_vigente"] == PRECIO_ECONOMICA


def test_detalle_de_un_vuelo_inexistente_responde_404(client: TestClient) -> None:
    """HU-19: un vuelo que no existe responde 404 con el formato único de error."""
    respuesta = client.get(ruta(999_999))

    assert respuesta.status_code == 404
    error = respuesta.json()["error"]
    assert error["codigo"] == "no_encontrado"
    assert error["mensaje"] == "El vuelo no existe."
    assert error.get("campos") is None
