"""RNF-10: cada endpoint del módulo responde 401 o 403 a los roles que no lo tienen permitido.

Matriz del contrato en docs/api/iteracion-1.md. Los endpoints que todavía son stubs responden
501 (o 422 si el cuerpo vacío no pasa la validación) al rol permitido.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol

PUBLICO = None
ADMIN = (Rol.ADMIN,)

ENDPOINTS: list[tuple[str, str, tuple[Rol, ...] | None]] = [
    ("GET", "/api/v1/ciudades", PUBLICO),
    ("GET", "/api/v1/vuelos", ADMIN),
    ("POST", "/api/v1/vuelos", ADMIN),
    ("POST", "/api/v1/vuelos/vista-previa", ADMIN),
    ("POST", "/api/v1/vuelos/recurrentes", ADMIN),
    ("POST", "/api/v1/vuelos/recurrentes/vista-previa", ADMIN),
    ("GET", "/api/v1/vuelos/1", PUBLICO),
    ("GET", "/api/v1/vuelos/1/gestion", ADMIN),
    ("PUT", "/api/v1/vuelos/1", ADMIN),
    ("POST", "/api/v1/vuelos/1/cancelar", ADMIN),
    ("GET", "/api/v1/vuelos/1/pasajeros", ADMIN),
    ("POST", "/api/v1/vuelos/1/promociones", ADMIN),
    ("GET", "/api/v1/promociones", ADMIN),
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_matriz_de_permisos(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # RF-11: solo los administradores gestionan vuelos y promociones.
    cliente_http = client_como(rol) if rol else client
    for metodo, ruta, permitidos in ENDPOINTS:
        estado = cliente_http.request(metodo, ruta, json={}).status_code
        if permitidos is PUBLICO or rol in permitidos:
            assert estado not in (401, 403), f"{metodo} {ruta} como {rol}: {estado}"
        else:
            esperado = 401 if rol is None else 403
            assert estado == esperado, f"{metodo} {ruta} como {rol}: {estado}"


def test_programar_vuelo_sin_sesion_responde_no_autenticado(client: TestClient):
    """HU-13 · RNF-10: sin sesión, POST /vuelos responde 401 no_autenticado."""
    respuesta = client.post("/api/v1/vuelos", json={})

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ROOT])
def test_programar_vuelo_solo_para_administradores(
    client_como: Callable[[Rol], TestClient], rol: Rol
):
    """HU-13 · RNF-10: un cliente o root recibe 403 sin_permiso al programar un vuelo."""
    respuesta = client_como(rol).post("/api/v1/vuelos", json={})

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "sin_permiso"


@pytest.mark.parametrize(
    "ruta",
    ["/api/v1/vuelos/recurrentes", "/api/v1/vuelos/recurrentes/vista-previa"],
)
def test_serie_sin_sesion_responde_no_autenticado(client: TestClient, ruta: str):
    """HU-14 · RNF-10: sin sesión, los endpoints de la serie responden 401 no_autenticado."""
    respuesta = client.post(ruta, json={})

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


@pytest.mark.parametrize(
    "ruta",
    ["/api/v1/vuelos/recurrentes", "/api/v1/vuelos/recurrentes/vista-previa"],
)
@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ROOT])
def test_serie_solo_para_administradores(
    client_como: Callable[[Rol], TestClient], rol: Rol, ruta: str
):
    """HU-14 · RNF-10: un cliente o root recibe 403 sin_permiso en los endpoints de la serie."""
    respuesta = client_como(rol).post(ruta, json={})

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "sin_permiso"


RUTAS_GESTION = [
    ("GET", "/api/v1/vuelos"),
    ("GET", "/api/v1/vuelos/1/gestion"),
    ("PUT", "/api/v1/vuelos/1"),
]


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_GESTION)
def test_gestion_de_vuelos_sin_sesion_responde_no_autenticado(
    client: TestClient, metodo: str, ruta: str
):
    """HU-15 · RNF-10: sin sesión, el listado y la edición de vuelos responden 401."""
    respuesta = client.request(metodo, ruta, json={})

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_GESTION)
@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ROOT])
def test_gestion_de_vuelos_solo_para_administradores(
    client_como: Callable[[Rol], TestClient], metodo: str, ruta: str, rol: Rol
):
    """HU-15 · RNF-10: un cliente o root recibe 403 sin_permiso en la gestión de vuelos."""
    respuesta = client_como(rol).request(metodo, ruta, json={})

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "sin_permiso"


RUTAS_PROMOCIONES = [
    ("POST", "/api/v1/vuelos/1/promociones"),
    ("GET", "/api/v1/promociones"),
]


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_PROMOCIONES)
def test_promociones_sin_sesion_responde_no_autenticado(client: TestClient, metodo: str, ruta: str):
    """HU-17 · RNF-10: sin sesión, las promociones responden 401 no_autenticado."""
    respuesta = client.request(metodo, ruta, json={})

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_PROMOCIONES)
@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ROOT])
def test_promociones_solo_para_administradores(
    client_como: Callable[[Rol], TestClient], metodo: str, ruta: str, rol: Rol
):
    """HU-17 · RNF-10: un cliente o root recibe 403 sin_permiso en promociones."""
    respuesta = client_como(rol).request(metodo, ruta, json={})

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "sin_permiso"
