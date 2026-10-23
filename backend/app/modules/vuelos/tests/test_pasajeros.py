"""Pasajeros de un vuelo y su ocupación por clase (HU-18, RF-21, SUP-25, SUP-26)."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import NoEncontrado
from app.modules.reservas import service as reservas_service
from app.modules.vuelos import service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import (
    crear_vuelo,
    iniciar_sesion_admin,
    simular_ocupacion,
)

AHORA = datetime(2026, 12, 10, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("tipo", "clase", "numero", "silla"),
    [
        ("nacional", "primera", 1, "1A"),
        ("nacional", "primera", 25, "5E"),
        ("nacional", "economica", 26, "6A"),
        ("nacional", "economica", 150, "30E"),
        ("internacional", "primera", 1, "1A"),
        ("internacional", "primera", 50, "10E"),
        ("internacional", "economica", 51, "11A"),
        ("internacional", "economica", 60, "11K"),
        ("internacional", "economica", 250, "30K"),
    ],
)
def test_nombre_de_silla(tipo: str, clase: str, numero: int, silla: str) -> None:
    """HU-18 · SUP-25, SUP-26: la silla se muestra como fila y letra según el Apéndice A."""
    assert service.nombre_de_silla(tipo, clase, numero) == silla


def simular_pasajeros(
    monkeypatch: pytest.MonkeyPatch, pasajeros: Sequence[reservas_service.PasajeroVuelo]
) -> None:
    """Sustituye `reservas.pasajeros_de_vuelo`, que hasta la iteración 2 devuelve vacío."""
    monkeypatch.setattr(
        reservas_service, "pasajeros_de_vuelo", lambda _db, _vuelo_id: list(pasajeros)
    )


def vuelo_realizado(db: Session, **cambios: Any) -> Vuelo:
    """Vuelo internacional que ya llegó, para el detalle de pasajeros (HU-18)."""
    base: dict[str, Any] = {
        "tipo": "internacional",
        "origen": "PEI",
        "destino": "MAD",
        "estado": "realizado",
        "salida": AHORA - timedelta(hours=12),
        "duracion_minutos": 600,
    }
    base.update(cambios)
    return crear_vuelo(db, **base)


def test_pasajeros_con_clase_y_silla_y_ocupacion_por_clase(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-18 · criterio 3 · RF-21: el detalle trae los pasajeros con su clase y su silla y la
    ocupación por clase."""
    vuelo = vuelo_realizado(db)
    simular_pasajeros(
        monkeypatch,
        [
            reservas_service.PasajeroVuelo(
                nombres="Ana", apellidos="Pérez", clase="economica", numero_silla=58
            ),
            reservas_service.PasajeroVuelo(
                nombres="Luis", apellidos="Mora", clase="primera", numero_silla=6
            ),
        ],
    )
    simular_ocupacion(
        monkeypatch,
        {vuelo.id: reservas_service.OcupacionVuelo(vendidas_primera=1, vendidas_economica=1)},
    )

    detalle = service.listar_pasajeros_vuelo(db, vuelo.id)

    assert [(pasajero.clase, pasajero.silla) for pasajero in detalle.pasajeros] == [
        ("economica", "11H"),
        ("primera", "2A"),
    ]
    assert detalle.ocupacion.vendidas_economica == 1
    assert detalle.ocupacion.vendidas_primera == 1
    assert detalle.vuelo.codigo == vuelo.codigo


def test_pasajeros_de_un_vuelo_sin_ventas_es_una_lista_vacia(db: Session) -> None:
    """HU-18: hasta la iteración 2 no hay compras y la lista de pasajeros viene vacía."""
    vuelo = vuelo_realizado(db)

    detalle = service.listar_pasajeros_vuelo(db, vuelo.id)

    assert detalle.pasajeros == []
    assert detalle.ocupacion.tiquetes_vendidos == 0


def test_pasajeros_de_un_vuelo_inexistente_no_encontrado(db: Session) -> None:
    """HU-18: un vuelo inexistente responde no_encontrado."""
    with pytest.raises(NoEncontrado) as error:
        service.listar_pasajeros_vuelo(db, 999_999)

    assert error.value.codigo == "no_encontrado"


def test_endpoint_de_pasajeros_devuelve_vuelo_ocupacion_y_pasajeros(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-18 · criterio 3: GET /vuelos/{id}/pasajeros responde con la forma del contrato."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = vuelo_realizado(db)
    simular_pasajeros(
        monkeypatch,
        [
            reservas_service.PasajeroVuelo(
                nombres="Ana", apellidos="Pérez", clase="economica", numero_silla=58
            )
        ],
    )

    respuesta = client.get(f"/api/v1/vuelos/{vuelo.id}/pasajeros")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["vuelo"]["codigo"] == vuelo.codigo
    assert cuerpo["vuelo"]["estado"] == "realizado"
    assert cuerpo["ocupacion"]["economica"] == {
        "capacidad": 200,
        "vendidas": 0,
        "reservadas": 0,
        "disponibles": 200,
    }
    assert cuerpo["pasajeros"] == [
        {
            "nombres": "Ana",
            "apellidos": "Pérez",
            "clase": "economica",
            "silla": "11H",
            "numero_silla": 58,
        }
    ]


def test_endpoint_de_pasajeros_de_un_vuelo_inexistente_responde_404(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-18: el endpoint responde 404 no_encontrado con el formato único de errores."""
    iniciar_sesion_admin(client, crear_usuario)

    respuesta = client.get("/api/v1/vuelos/999999/pasajeros")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "no_encontrado"
