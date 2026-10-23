"""Bloqueo por registro incompleto (issue #15: HU-12, RF-02, RF-11)."""

import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import (
    PREFIJOS_PERMITIDOS_CON_REGISTRO_INCOMPLETO,
    RUTAS_PERMITIDAS_CON_REGISTRO_INCOMPLETO,
    get_current_user,
    get_current_user_opcional,
    permitida_con_registro_incompleto,
)
from app.core.errors import RegistroIncompleto
from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.main import API_PREFIX, app

RUTA_REGISTRO = "/api/v1/administradores/me/registro"
_SESION = {get_current_user, get_current_user_opcional}


def _llamadas(dependant: Any) -> set[Any]:
    llamadas: set[Any] = set()
    for sub in dependant.dependencies:
        llamadas.add(sub.call)
        llamadas |= _llamadas(sub)
    return llamadas


def _rutas_con_sesion() -> list[tuple[str, str]]:
    """(método, ruta) de cada endpoint de la app que depende de la sesión, de todos los módulos."""
    rutas = []
    for contexto in iter_route_contexts(app.routes):
        # /_pruebas: rutas que agregan otros tests de core al app global.
        if not isinstance(contexto.original_route, APIRoute) or "/_pruebas" in contexto.path:
            continue
        if _llamadas(contexto.dependant).isdisjoint(_SESION):
            continue
        rutas.extend((metodo, contexto.path) for metodo in contexto.methods)
    return sorted(rutas)


CON_SESION = _rutas_con_sesion()
BLOQUEADAS = [r for r in CON_SESION if not permitida_con_registro_incompleto(*r)]
EXENTAS = [r for r in CON_SESION if permitida_con_registro_incompleto(*r)]


def _ids(rutas: list[tuple[str, str]]) -> list[str]:
    return [f"{metodo} {ruta}" for metodo, ruta in rutas]


def _concreta(ruta: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", ruta)


def _codigo(respuesta: Any) -> str | None:
    try:
        return respuesta.json()["error"]["codigo"]
    except (ValueError, KeyError, TypeError):
        return None


def _iniciar_sesion(client: TestClient, usuario: Any) -> Any:
    return client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )


@pytest.fixture
def admin_incompleto(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> tuple[TestClient, Any]:
    """Cliente HTTP con la sesión de un administrador con el registro incompleto."""
    usuario = crear_usuario(Rol.ADMIN, registro_completo=False)
    assert _iniciar_sesion(client, usuario).status_code == 200
    return client, usuario


def test_el_descubrimiento_cubre_los_endpoints_protegidos_de_todos_los_modulos():
    """HU-12: la lista de rutas bloqueadas sale de la app, no de una lista escrita a mano."""
    bloqueadas = set(BLOQUEADAS)
    exentas = set(EXENTAS)
    assert ("GET", "/api/v1/vuelos") in bloqueadas
    assert ("GET", "/api/v1/promociones") in bloqueadas
    assert ("PUT", "/api/v1/usuarios/me/contrasena") in bloqueadas
    assert ("GET", "/api/v1/administradores") in bloqueadas
    assert ("POST", "/api/v1/usuarios/registro") in bloqueadas
    assert ("GET", "/api/v1/auth/me") in exentas
    assert ("POST", "/api/v1/auth/logout") in exentas
    assert ("POST", RUTA_REGISTRO) in exentas
    assert ("GET", "/api/v1/ciudades") not in set(CON_SESION)


@pytest.mark.parametrize(("metodo", "ruta"), BLOQUEADAS, ids=_ids(BLOQUEADAS))
def test_admin_con_registro_incompleto_solo_puede_completar_el_registro(
    admin_incompleto: tuple[TestClient, Any], metodo: str, ruta: str
):
    """HU-12, criterio 1: toda ruta con sesión fuera de la lista permitida responde 403."""
    client, _ = admin_incompleto
    respuesta = client.request(metodo, _concreta(ruta), json={})
    assert respuesta.status_code == 403
    assert respuesta.json() == {
        "error": {"codigo": "registro_incompleto", "mensaje": RegistroIncompleto.mensaje}
    }


@pytest.mark.parametrize(("metodo", "ruta"), EXENTAS, ids=_ids(EXENTAS))
def test_las_rutas_permitidas_siguen_respondiendo(
    admin_incompleto: tuple[TestClient, Any], metodo: str, ruta: str
):
    """HU-12: las rutas permitidas no responden 403 aunque el registro esté incompleto."""
    client, _ = admin_incompleto
    assert client.request(metodo, _concreta(ruta), json={}).status_code != 403


def test_login_me_y_logout_responden_con_el_registro_incompleto(
    client: TestClient, crear_usuario: Callable[..., Any]
):
    """HU-12, RF-11: el administrador incompleto puede iniciar sesión, ver /auth/me y salir."""
    usuario = crear_usuario(Rol.ADMIN, registro_completo=False)
    assert _iniciar_sesion(client, usuario).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_completar_el_registro_no_choca_con_el_bloqueo(admin_incompleto: tuple[TestClient, Any]):
    """HU-12: el endpoint que completa el registro usa la sesión y no queda bloqueado."""
    client, _ = admin_incompleto
    assert ("POST", RUTA_REGISTRO) in CON_SESION
    assert client.post(RUTA_REGISTRO, json={}).status_code != 403


def test_al_completar_el_registro_la_misma_sesion_queda_habilitada(
    admin_incompleto: tuple[TestClient, Any], db: Session
):
    """HU-12, criterio 2: al completar el registro la sesión abierta ya puede usar todo."""
    client, usuario = admin_incompleto
    assert client.get("/api/v1/vuelos").status_code == 403
    usuario.registro_completo = True
    db.commit()
    assert client.get("/api/v1/vuelos").status_code == 200


@pytest.mark.parametrize("rol", [Rol.ADMIN, Rol.CLIENTE, Rol.ROOT])
@pytest.mark.parametrize(("metodo", "ruta"), BLOQUEADAS, ids=_ids(BLOQUEADAS))
def test_otros_usuarios_no_se_ven_afectados(
    client_como: Callable[[Rol], TestClient], rol: Rol, metodo: str, ruta: str
):
    """HU-12: con el registro completo, ningún rol recibe `registro_incompleto`."""
    respuesta = client_como(rol).request(metodo, _concreta(ruta), json={})
    assert _codigo(respuesta) != "registro_incompleto"


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ROOT])
def test_el_bloqueo_solo_aplica_a_administradores(
    client: TestClient, crear_usuario: Callable[..., Any], rol: Rol
):
    """HU-12: el bloqueo es solo para administradores, aunque otro rol tenga el indicador falso."""
    usuario = crear_usuario(rol, registro_completo=False)
    assert _iniciar_sesion(client, usuario).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.put("/api/v1/usuarios/me/contrasena", json={}).status_code == 422


def test_rutas_permitidas_por_metodo_y_ruta_y_alineadas_con_el_prefijo():
    """HU-12: la lista permitida distingue método y ruta, y usa el prefijo real de la API."""
    assert permitida_con_registro_incompleto("POST", RUTA_REGISTRO)
    assert permitida_con_registro_incompleto("POST", "/api/v1/auth/login")
    assert permitida_con_registro_incompleto("GET", "/api/v1/auth/me")
    assert not permitida_con_registro_incompleto("GET", RUTA_REGISTRO)
    assert not permitida_con_registro_incompleto("GET", "/api/v1/authx")
    assert not permitida_con_registro_incompleto("GET", "/api/v1/vuelos")
    permitidas = [
        *PREFIJOS_PERMITIDOS_CON_REGISTRO_INCOMPLETO,
        *(ruta for _, ruta in RUTAS_PERMITIDAS_CON_REGISTRO_INCOMPLETO),
    ]
    assert all(p.startswith(API_PREFIX + "/") for p in permitidas)
