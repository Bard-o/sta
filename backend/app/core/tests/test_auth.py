from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.core.auth import UsuarioActual, require_role
from app.core.config import get_settings
from app.core.security import Rol
from app.main import app

# Rutas de prueba para ejercitar require_role sin depender de un módulo real.
_router = APIRouter(prefix="/api/v1/_pruebas")


@_router.get("/solo-admin")
def _solo_admin(
    usuario: Annotated[UsuarioActual, Depends(require_role(Rol.ADMIN))],
) -> dict[str, str]:
    return {"rol": usuario.rol.value}


@_router.get("/root-o-admin", dependencies=[Depends(require_role(Rol.ROOT, Rol.ADMIN))])
def _root_o_admin() -> dict[str, bool]:
    return {"ok": True}


app.include_router(_router)


def test_sin_sesion_responde_401(client: TestClient):
    respuesta = client.get("/api/v1/_pruebas/solo-admin")
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


@pytest.mark.parametrize(
    ("rol", "esperado"), [(Rol.ADMIN, 200), (Rol.ROOT, 403), (Rol.CLIENTE, 403)]
)
def test_require_role_un_rol(client_como: Callable[[Rol], TestClient], rol: Rol, esperado: int):
    # RNF-10: la autorización se verifica en el servidor.
    respuesta = client_como(rol).get("/api/v1/_pruebas/solo-admin")
    assert respuesta.status_code == esperado
    if esperado == 403:
        assert respuesta.json()["error"]["codigo"] == "sin_permiso"


@pytest.mark.parametrize(
    ("rol", "esperado"), [(Rol.ADMIN, 200), (Rol.ROOT, 200), (Rol.CLIENTE, 403)]
)
def test_require_role_varios_roles(
    client_como: Callable[[Rol], TestClient], rol: Rol, esperado: int
):
    assert client_como(rol).get("/api/v1/_pruebas/root-o-admin").status_code == esperado


def test_token_vencido_responde_401(client: TestClient, crear_usuario):
    # RNF-14: tras el tiempo de inactividad, la siguiente petición pide iniciar sesión.
    usuario = crear_usuario(Rol.CLIENTE)
    settings = get_settings()
    hace_una_hora = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {
            "sub": str(usuario.id),
            "rol": "cliente",
            "sv": 0,
            "iat": hace_una_hora,
            "exp": hace_una_hora + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    respuesta = client.get("/api/v1/auth/me", headers={"Cookie": f"{settings.cookie_name}={token}"})
    assert respuesta.status_code == 401
