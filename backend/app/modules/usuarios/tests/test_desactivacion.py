"""HU-09: desactivar la cuenta del cliente (RF-10).

En la iteración 1 reservas todavía no tiene compras ni reservas, así que la regla que bloquea
la desactivación se simula con monkeypatch sobre su función pública.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.reservas import service as reservas_service
from app.modules.reservas.service import TiqueteActivo
from app.modules.usuarios.models import Usuario

RUTA = "/api/v1/usuarios/me/desactivacion"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def _cliente_con_sesion(client: TestClient, crear_usuario: Callable[..., Any]) -> Usuario:
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez", email="laura@example.com")
    respuesta = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert respuesta.status_code == 200, respuesta.text
    return usuario


def _con_bloqueos(monkeypatch: pytest.MonkeyPatch, bloqueos: list[TiqueteActivo]) -> None:
    monkeypatch.setattr(
        reservas_service,
        "tiquetes_activos_futuros_de_cliente",
        lambda db, usuario_id: bloqueos,
    )


def _sin_bloqueos(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_bloqueos(monkeypatch, [])


def _bloqueo(**cambios: Any) -> TiqueteActivo:
    datos: dict[str, Any] = {
        "tipo": "compra",
        "codigo_reserva": "K7Q2MX",
        "vuelo_id": 88,
        "vuelo_codigo": "STA-00088",
        "origen": "Bogotá",
        "destino": "Madrid",
        "salida": datetime(2026, 12, 11, 3, tzinfo=UTC),
    }
    datos.update(cambios)
    return TiqueteActivo(**datos)


def test_desactivar_cierra_la_sesion_y_el_nuevo_login_responde_cuenta_inactiva(
    client: TestClient, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # HU-09 CA-1: tras confirmar, la sesión se cierra y un nuevo inicio responde «cuenta inactiva».
    usuario = _cliente_con_sesion(client, crear_usuario)
    _sin_bloqueos(monkeypatch)
    nombre_cookie = get_settings().cookie_name
    token_anterior = client.cookies.get(nombre_cookie)

    respuesta = client.post(RUTA)
    assert respuesta.status_code == 204, respuesta.text
    assert client.cookies.get(nombre_cookie) is None

    reuso = client.get(ME, headers={"Cookie": f"{nombre_cookie}={token_anterior}"})
    assert reuso.status_code == 401
    assert reuso.json()["error"]["codigo"] == "no_autenticado"

    login = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert login.status_code == 403
    assert login.json()["error"]["codigo"] == "cuenta_inactiva"


def test_desactivar_conserva_los_registros_marcados_como_inactivos(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # HU-09 CA-2: los registros siguen en la base de datos, marcados como inactivos.
    usuario = _cliente_con_sesion(client, crear_usuario)
    _sin_bloqueos(monkeypatch)
    db.refresh(usuario)
    antes = (
        usuario.nombre_usuario,
        usuario.email,
        usuario.password_hash,
        usuario.email_verificado,
        usuario.fecha_aceptacion_politica,
    )
    total_antes = db.scalar(select(func.count()).select_from(Usuario))

    assert client.post(RUTA).status_code == 204

    db.expire_all()
    guardado = db.get(Usuario, usuario.id)
    assert guardado is not None
    assert guardado.activo is False
    assert (
        guardado.nombre_usuario,
        guardado.email,
        guardado.password_hash,
        guardado.email_verificado,
        guardado.fecha_aceptacion_politica,
    ) == antes
    assert db.scalar(select(func.count()).select_from(Usuario)) == total_antes


def test_con_tiquetes_activos_rechaza_la_desactivacion(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # HU-09 CA-3: con compras o reservas activas en vuelos futuros la desactivación se rechaza
    # con 409 tiquetes_activos y la cuenta sigue activa.
    usuario = _cliente_con_sesion(client, crear_usuario)
    _con_bloqueos(monkeypatch, [_bloqueo()])

    respuesta = client.post(RUTA)
    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "error": {
            "codigo": "tiquetes_activos",
            "mensaje": "Tienes compras o reservas activas en vuelos futuros.",
        }
    }

    db.refresh(usuario)
    assert usuario.activo is True
    assert client.get(ME).status_code == 200


def test_get_indica_que_no_se_puede_desactivar_y_lista_los_bloqueos(
    client: TestClient, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # HU-09 CA-3: se listan las compras o reservas que el cliente debe cancelar o esperar.
    _cliente_con_sesion(client, crear_usuario)
    _con_bloqueos(
        monkeypatch,
        [
            _bloqueo(),
            _bloqueo(
                tipo="reserva",
                codigo_reserva=None,
                vuelo_id=90,
                vuelo_codigo="STA-00090",
                origen="Cali",
                destino="Bogotá",
                salida=datetime(2027, 1, 15, 14, 30, tzinfo=UTC),
            ),
        ],
    )

    respuesta = client.get(RUTA)
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "puede_desactivar": False,
        "bloqueos": [
            {
                "tipo": "compra",
                "codigo_reserva": "K7Q2MX",
                "vuelo_id": 88,
                "vuelo_codigo": "STA-00088",
                "origen": "Bogotá",
                "destino": "Madrid",
                "salida": "2026-12-11T03:00:00Z",
            },
            {
                "tipo": "reserva",
                "codigo_reserva": None,
                "vuelo_id": 90,
                "vuelo_codigo": "STA-00090",
                "origen": "Cali",
                "destino": "Bogotá",
                "salida": "2027-01-15T14:30:00Z",
            },
        ],
    }


def test_get_indica_que_se_puede_desactivar_sin_bloqueos(
    client: TestClient, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Contrato HU-09: sin compras ni reservas activas, el botón queda habilitado.
    _cliente_con_sesion(client, crear_usuario)
    _sin_bloqueos(monkeypatch)

    respuesta = client.get(RUTA)
    assert respuesta.status_code == 200
    assert respuesta.json() == {"puede_desactivar": True, "bloqueos": []}


def test_desactivar_consulta_los_bloqueos_del_modulo_reservas(
    client: TestClient, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # La regla de qué impide la desactivación vive en reservas: usuarios no la duplica.
    usuario = _cliente_con_sesion(client, crear_usuario)
    consultas: list[int] = []

    def falso(db: Session, usuario_id: int) -> list[TiqueteActivo]:
        consultas.append(usuario_id)
        return []

    monkeypatch.setattr(reservas_service, "tiquetes_activos_futuros_de_cliente", falso)

    assert client.post(RUTA).status_code == 204
    assert consultas == [usuario.id]
