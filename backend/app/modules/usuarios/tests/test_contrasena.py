"""HU-06: cambiar la contraseña indicando la actual (RF-01, RF-08, RNF-08)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import MENSAJE_POLITICA_CONTRASENA, Rol, verificar_contrasena
from app.core.testing import CONTRASENA_TEST

RUTA = "/api/v1/usuarios/me/contrasena"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
NUEVA = "OtraClave99"


def _sesion(rol: Rol, client: TestClient, crear_usuario: Callable[..., Any]) -> Any:
    usuario = crear_usuario(rol)
    respuesta = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert respuesta.status_code == 200, respuesta.text
    return usuario


def _cambiar(
    client: TestClient,
    *,
    actual: str = CONTRASENA_TEST,
    nueva: str = NUEVA,
    confirmacion: str | None = None,
) -> Any:
    return client.put(
        RUTA,
        json={
            "contrasena_actual": actual,
            "contrasena_nueva": nueva,
            "confirmacion": nueva if confirmacion is None else confirmacion,
        },
    )


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ADMIN, Rol.ROOT])
def test_cambia_la_contrasena_y_la_anterior_deja_de_funcionar(
    rol: Rol, client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    # HU-06 CA-1 (cliente, admin y root): con la actual correcta y una nueva válida, el cambio
    # se guarda y la anterior deja de funcionar.
    usuario = _sesion(rol, client, crear_usuario)

    respuesta = _cambiar(client)
    assert respuesta.status_code == 204, respuesta.text

    db.refresh(usuario)
    # RNF-08: se guarda el hash, nunca la contraseña en texto plano.
    assert usuario.password_hash != NUEVA
    assert usuario.password_hash.startswith("$argon2")
    assert verificar_contrasena(NUEVA, usuario.password_hash)
    assert not verificar_contrasena(CONTRASENA_TEST, usuario.password_hash)

    anterior = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert anterior.status_code == 401
    assert anterior.json()["error"]["codigo"] == "credenciales_invalidas"

    nueva = client.post(LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": NUEVA})
    assert nueva.status_code == 200


def test_contrasena_actual_incorrecta_no_cambia_nada(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    # HU-06 CA-2: si la contraseña actual es incorrecta, no se cambia nada.
    usuario = _sesion(Rol.CLIENTE, client, crear_usuario)
    hash_antes = usuario.password_hash

    respuesta = _cambiar(client, actual="NoEsLaClave1")

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "error": {
            "codigo": "contrasena_actual_incorrecta",
            "mensaje": "La contraseña actual es incorrecta.",
            "campos": {"contrasena_actual": "La contraseña actual es incorrecta."},
        }
    }
    db.refresh(usuario)
    assert usuario.password_hash == hash_antes
    # La contraseña original sigue funcionando.
    original = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert original.status_code == 200


@pytest.mark.parametrize(
    "nueva", ["Clave12", "12345678", "abcdefgh"], ids=["corta", "sin-letra", "sin-numero"]
)
def test_rechaza_contrasena_nueva_que_no_cumple_la_politica(
    nueva: str, client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    # HU-06 CA-3 (política) y RNF-08: mínimo 8 caracteres, al menos una letra y un número.
    usuario = _sesion(Rol.CLIENTE, client, crear_usuario)
    hash_antes = usuario.password_hash

    respuesta = _cambiar(client, nueva=nueva)

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "error": {
            "codigo": "datos_invalidos",
            "mensaje": "Revisa los campos marcados.",
            "campos": {"contrasena_nueva": MENSAJE_POLITICA_CONTRASENA},
        }
    }
    db.refresh(usuario)
    assert usuario.password_hash == hash_antes


def test_rechaza_confirmacion_que_no_coincide(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    # HU-06 CA-3 (confirmación): si la nueva no coincide con la confirmación, se rechaza.
    usuario = _sesion(Rol.CLIENTE, client, crear_usuario)
    hash_antes = usuario.password_hash

    respuesta = _cambiar(client, confirmacion="OtraClave98")

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "error": {
            "codigo": "datos_invalidos",
            "mensaje": "Revisa los campos marcados.",
            "campos": {"confirmacion": "Las contraseñas no coinciden."},
        }
    }
    db.refresh(usuario)
    assert usuario.password_hash == hash_antes


def test_la_sesion_actual_sigue_abierta(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    # HU-06: la sesión actual sigue abierta tras cambiar la contraseña (a diferencia de HU-05).
    usuario = _sesion(Rol.CLIENTE, client, crear_usuario)
    version_antes = usuario.version_sesion

    assert _cambiar(client).status_code == 204

    db.refresh(usuario)
    assert usuario.version_sesion == version_antes
    me = client.get(ME)
    assert me.status_code == 200
    assert me.json()["nombre_usuario"] == usuario.nombre_usuario


def test_sin_sesion_responde_401_no_autenticado(client: TestClient) -> None:
    # RNF-10: el endpoint exige sesión de cualquier rol; un visitante recibe 401.
    respuesta = _cambiar(client)
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"
