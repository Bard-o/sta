"""RNF-10: cada endpoint del módulo responde 401 o 403 a los roles que no lo tienen permitido.

Matriz del contrato en docs/api/iteracion-2.md. Los endpoints que todavía son stubs responden
501 (o 422 si el cuerpo vacío no pasa la validación) al rol permitido.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.reservas.tests.apoyo import cliente_con_perfil, entrada
from app.modules.vuelos.tests.fabricas import crear_vuelo

CLIENTE = (Rol.CLIENTE,)

ENDPOINTS: list[tuple[str, str, tuple[Rol, ...]]] = [
    ("POST", "/api/v1/reservas", CLIENTE),
    ("POST", "/api/v1/reservas/1/pagar", CLIENTE),
    ("POST", "/api/v1/compras", CLIENTE),
    ("GET", "/api/v1/compras/1", CLIENTE),
    ("POST", "/api/v1/compras/1/confirmar", CLIENTE),
    ("DELETE", "/api/v1/compras/1", CLIENTE),
    ("GET", "/api/v1/mis-viajes?tipo=reserva", CLIENTE),
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_matriz_de_permisos(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # Apéndice B, RNF-10: reservar, comprar y ver Mis viajes es solo del cliente: ni el
    # administrador ni el root pueden crear reservas o compras.
    cliente_http = client_como(rol) if rol else client
    for metodo, ruta, permitidos in ENDPOINTS:
        respuesta = cliente_http.request(metodo, ruta, json={})
        if rol in permitidos:
            assert respuesta.status_code not in (401, 403), f"{metodo} {ruta} como {rol}"
        else:
            esperado, codigo = (401, "no_autenticado") if rol is None else (403, "sin_permiso")
            assert respuesta.status_code == esperado, f"{metodo} {ruta} como {rol}"
            assert respuesta.json()["error"]["codigo"] == codigo, f"{metodo} {ruta} como {rol}"


def _login(client: TestClient, usuario: object) -> None:
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200


def _cuerpo(vuelo: object) -> dict[str, object]:
    return entrada([vuelo]).model_dump(mode="json")


def test_hu24_un_correo_sin_verificar_no_puede_reservar(
    db: Session, client: TestClient, crear_usuario: Callable[..., object]
) -> None:
    """HU-02 · HU-24: con la sesión iniciada pero el correo sin verificar, POST /reservas

    responde 403 `correo_no_verificado` y no crea la reserva.
    """
    cliente = cliente_con_perfil(
        db, crear_usuario, verificado=False, nombre_usuario="api_sin_verificar"
    )
    vuelo = crear_vuelo(db, salida=datetime.now(UTC) + timedelta(days=30))
    _login(client, cliente)

    respuesta = client.post("/api/v1/reservas", json=_cuerpo(vuelo))

    assert respuesta.status_code == 403
    error = respuesta.json()["error"]
    assert error["codigo"] == "correo_no_verificado"
    assert error["mensaje"] == "Verifica tu correo para reservar o comprar."


def test_hu24_el_cliente_verificado_reserva_por_la_api(
    db: Session, client: TestClient, crear_usuario: Callable[..., object]
) -> None:
    """HU-24: el cliente con el correo verificado recibe 201 con la reserva y sus tiquetes."""
    cliente = cliente_con_perfil(db, crear_usuario, nombre_usuario="api_reserva")
    vuelo = crear_vuelo(db, salida=datetime.now(UTC) + timedelta(days=30))
    _login(client, cliente)

    respuesta = client.post("/api/v1/reservas", json=_cuerpo(vuelo))

    assert respuesta.status_code == 201
    reserva = respuesta.json()
    assert reserva["tipo"] == "reserva"
    assert reserva["estado"] == "vigente"
    assert len(reserva["codigo"]) == 6
    assert reserva["total"] == vuelo.precio_economica
    assert reserva["total_pendiente"] == vuelo.precio_economica
    assert len(reserva["tramos"]) == 1
    assert reserva["tramos"][0]["vuelo"]["codigo"] == vuelo.codigo
    assert len(reserva["viajeros"]) == 1
    assert reserva["viajeros"][0]["tiquetes"][0]["estado"] == "reservado"
    assert reserva["viajeros"][0]["tiquetes"][0]["clase"] == "economica"
