from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.usuarios import service
from app.modules.usuarios.models import Usuario

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"


def _login(client: TestClient, usuario: str, contrasena: str = CONTRASENA_TEST):
    return client.post(LOGIN, json={"usuario": usuario, "contrasena": contrasena})


def test_login_correcto_pone_cookie_httponly_y_devuelve_el_usuario(
    client: TestClient, crear_usuario
):
    # HU-03: con credenciales correctas, el usuario entra con su rol.
    crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez", email="laura@example.com")
    respuesta = _login(client, "lauragomez")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre_usuario"] == "lauragomez"
    assert cuerpo["rol"] == "cliente"
    assert "password_hash" not in cuerpo
    set_cookie = respuesta.headers["set-cookie"]
    assert set_cookie.startswith(f"{get_settings().cookie_name}=")
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_login_con_correo_sin_importar_mayusculas(client: TestClient, crear_usuario):
    crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez", email="laura@example.com")
    assert _login(client, "Laura@Example.com").status_code == 200


def test_credenciales_incorrectas_no_revelan_que_fallo(client: TestClient, crear_usuario):
    # RF-06 / HU-03: mismo mensaje si falla el usuario o la contraseña.
    crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez")
    contrasena_errada = _login(client, "lauragomez", "Otra12345")
    usuario_inexistente = _login(client, "nadie")

    assert contrasena_errada.status_code == usuario_inexistente.status_code == 401
    assert contrasena_errada.json() == usuario_inexistente.json()
    assert contrasena_errada.json()["error"] == {
        "codigo": "credenciales_invalidas",
        "mensaje": "Usuario o contraseña incorrectos.",
    }


def test_cuenta_inactiva(client: TestClient, crear_usuario):
    # HU-03: una cuenta desactivada recibe «cuenta inactiva».
    crear_usuario(Rol.ADMIN, nombre_usuario="admin_viejo", activo=False)
    respuesta = _login(client, "admin_viejo")
    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "cuenta_inactiva"


def test_cuenta_inactiva_no_se_revela_sin_la_contrasena(client: TestClient, crear_usuario):
    crear_usuario(Rol.ADMIN, nombre_usuario="admin_viejo", activo=False)
    assert _login(client, "admin_viejo", "Otra12345").json()["error"]["codigo"] == (
        "credenciales_invalidas"
    )


def test_me_sin_sesion_responde_401(client: TestClient):
    respuesta = client.get(ME)
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


def test_me_con_sesion(client_como: Callable[[Rol], TestClient]):
    respuesta = client_como(Rol.ROOT).get(ME)
    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "root"


def test_logout_invalida_la_sesion_en_el_servidor(client_como: Callable[[Rol], TestClient]):
    # HU-04: cualquier petición posterior con la sesión anterior es rechazada.
    client = client_como(Rol.CLIENTE)
    nombre_cookie = get_settings().cookie_name
    token_anterior = client.cookies.get(nombre_cookie)

    respuesta = client.post(LOGOUT)
    assert respuesta.status_code == 204
    assert client.cookies.get(nombre_cookie) is None

    reuso = client.get(ME, headers={"Cookie": f"{nombre_cookie}={token_anterior}"})
    assert reuso.status_code == 401


def test_logout_sin_sesion_responde_204(client: TestClient):
    assert client.post(LOGOUT).status_code == 204


def test_asegurar_root_crea_un_solo_root(db: Session):
    # RF-01: tras la instalación existe exactamente un usuario root.
    assert service.asegurar_root(db, "root", "Clave1234") is True
    assert service.asegurar_root(db, "otro_root", "Clave5678") is False
    total = db.scalar(select(func.count()).select_from(Usuario).where(Usuario.rol == Rol.ROOT))
    assert total == 1
