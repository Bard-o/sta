"""Constructores de vuelos para los tests del módulo."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.reservas import service as reservas_service
from app.modules.vuelos.models import EstadoVuelo, TipoVuelo, Vuelo

SALIDA = datetime(2026, 12, 10, 11, 0, tzinfo=UTC)
CAPACIDADES = {"nacional": (25, 125), "internacional": (50, 200)}


def crear_vuelo(
    db: Session,
    *,
    origen: str = "PEI",
    destino: str = "BOG",
    salida: datetime = SALIDA,
    duracion_minutos: int = 50,
    tipo: TipoVuelo = "nacional",
    estado: EstadoVuelo = "programado",
    **cambios: Any,
) -> Vuelo:
    """Inserta un vuelo directamente en la base para probar duplicados y estados."""
    primera, economica = CAPACIDADES[tipo]
    datos: dict[str, Any] = {
        "tipo": tipo,
        "origen_codigo": origen,
        "destino_codigo": destino,
        "salida": salida,
        "duracion_minutos": duracion_minutos,
        "precio_economica": 280_000,
        "precio_primera": 750_000,
        "capacidad_primera": primera,
        "capacidad_economica": economica,
        "estado": estado,
    }
    datos.update(cambios)
    datos["llegada"] = datos["salida"] + timedelta(minutes=datos["duracion_minutos"])

    vuelo = Vuelo(**datos)
    db.add(vuelo)
    db.flush()
    db.refresh(vuelo)
    return vuelo


def cuerpo_vuelo(**cambios: object) -> dict[str, object]:
    """Cuerpo válido de `VueloEntrada` para los tests de los endpoints."""
    base: dict[str, object] = {
        "origen": "PEI",
        "destino": "MAD",
        "fecha_salida": "2099-01-15",
        "hora_salida": "10:00",
        "duracion_minutos": 600,
        "precio_economica": 2_450_000,
        "precio_primera": 6_900_000,
    }
    base.update(cambios)
    return base


def iniciar_sesion_admin(client: TestClient, crear_usuario: Callable[..., Any]) -> Any:
    """Crea un administrador y abre su sesión en el cliente. Devuelve el usuario."""
    usuario = crear_usuario(Rol.ADMIN)
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200, respuesta.text
    return usuario


def simular_ocupacion(
    monkeypatch: pytest.MonkeyPatch,
    por_vuelo: dict[int, reservas_service.OcupacionVuelo] | None = None,
) -> None:
    """Sustituye `reservas.ocupacion_de_vuelos` para simular ventas y reservas (HU-15).

    Hasta la iteración 2 el módulo reservas todavía no tiene datos reales.
    """
    ocupaciones = por_vuelo or {}

    def _ocupacion(
        _db: Session, vuelo_ids: Sequence[int]
    ) -> dict[int, reservas_service.OcupacionVuelo]:
        return {
            vuelo_id: ocupaciones.get(vuelo_id, reservas_service.OcupacionVuelo())
            for vuelo_id in vuelo_ids
        }

    monkeypatch.setattr(reservas_service, "ocupacion_de_vuelos", _ocupacion)
