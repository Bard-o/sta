from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest
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


def _reloj_controlado(monkeypatch: pytest.MonkeyPatch, ahora: datetime) -> dict[str, datetime]:
    """Sustituye el reloj del service para probar el bloqueo sin esperar 15 minutos reales."""
    reloj = {"ahora": ahora}
    monkeypatch.setattr(service, "_ahora_utc", lambda: reloj["ahora"])
    return reloj


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
    assert respuesta.json()["error"] == {
        "codigo": "cuenta_inactiva",
        "mensaje": "Cuenta inactiva.",
    }


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


@pytest.mark.parametrize("rol", list(Rol), ids=lambda rol: rol.value)
def test_login_con_credenciales_correctas_devuelve_el_rol(
    rol: Rol, client: TestClient, crear_usuario
):
    # HU-03: con credenciales correctas el usuario entra al inicio de su rol.
    usuario = crear_usuario(rol, nombre_usuario=f"cuenta_{rol.value}")
    respuesta = _login(client, usuario.nombre_usuario)
    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == rol.value


def test_usuario_salida_trae_registro_completo_y_nombres_para_cada_rol(
    client: TestClient, db: Session, crear_usuario
):
    # HU-03: el login y /auth/me traen registro_completo, nombres y apellidos reales.
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_campos")
    cliente.nombres = "Laura"
    cliente.apellidos = "Gómez Ríos"
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="admin_campos")
    admin.nombres = "Carlos"
    admin.apellidos = "Ruiz"
    root = crear_usuario(Rol.ROOT, nombre_usuario="root_campos")
    db.commit()

    for usuario, nombres, apellidos in (
        (cliente, "Laura", "Gómez Ríos"),
        (admin, "Carlos", "Ruiz"),
        (root, None, None),
    ):
        respuesta = _login(client, usuario.nombre_usuario)
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["registro_completo"] is True
        assert cuerpo["nombres"] == nombres
        assert cuerpo["apellidos"] == apellidos

    # /auth/me devuelve el mismo cuerpo que el login.
    me = client.get(ME)
    assert me.status_code == 200
    assert me.json()["nombre_usuario"] == root.nombre_usuario
    assert me.json()["nombres"] is None
    assert me.json()["apellidos"] is None


def test_administrador_con_registro_incompleto(client: TestClient, db: Session, crear_usuario):
    # HU-03 / HU-12: el administrador pendiente de completar su registro trae false y sin nombre.
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="admin_pendiente")
    admin.registro_completo = False
    admin.nombres = None
    admin.apellidos = None
    db.commit()

    respuesta = _login(client, admin.nombre_usuario)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["registro_completo"] is False
    assert cuerpo["nombres"] is None
    assert cuerpo["apellidos"] is None


def test_quinto_intento_fallido_bloquea_y_el_sexto_responde_429(
    client: TestClient, db: Session, crear_usuario
):
    # HU-03 / RNF-13: tras 5 intentos fallidos, el sexto se rechaza aunque la clave sea correcta.
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="cuenta_bloqueada")

    for intento in range(1, service.MAX_INTENTOS_FALLIDOS + 1):
        respuesta = _login(client, usuario.nombre_usuario, "Otra12345")
        assert respuesta.status_code == 401, f"intento {intento}"

    db.refresh(usuario)
    assert usuario.intentos_fallidos == service.MAX_INTENTOS_FALLIDOS
    assert usuario.bloqueado_hasta is not None

    sexto = _login(client, usuario.nombre_usuario)
    assert sexto.status_code == 429
    error = sexto.json()["error"]
    assert set(error) == {"codigo", "mensaje"}
    assert error["codigo"] == "demasiados_intentos"
    assert error["mensaje"] == "Cuenta bloqueada. Intenta de nuevo en 15 minutos."
    assert 1 <= int(sexto.headers["Retry-After"]) <= 900


def test_desbloqueo_a_los_15_minutos_con_el_reloj_controlado(
    client: TestClient,
    db: Session,
    crear_usuario,
    monkeypatch: pytest.MonkeyPatch,
):
    # HU-03 / RNF-13: el bloqueo vence a los 15 minutos y el contador vuelve a cero.
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="cuenta_reloj")
    inicio = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    reloj = _reloj_controlado(monkeypatch, inicio)

    for _ in range(service.MAX_INTENTOS_FALLIDOS):
        assert _login(client, usuario.nombre_usuario, "Otra12345").status_code == 401

    reloj["ahora"] = inicio + timedelta(minutes=15) - timedelta(seconds=1)
    bloqueado = _login(client, usuario.nombre_usuario)
    assert bloqueado.status_code == 429
    assert bloqueado.headers["Retry-After"] == "1"
    assert bloqueado.json()["error"]["mensaje"] == (
        "Cuenta bloqueada. Intenta de nuevo en 1 minuto."
    )

    reloj["ahora"] = inicio + timedelta(minutes=15)
    desbloqueado = _login(client, usuario.nombre_usuario)
    assert desbloqueado.status_code == 200
    db.refresh(usuario)
    assert usuario.intentos_fallidos == 0
    assert usuario.bloqueado_hasta is None


def test_login_correcto_reinicia_el_contador_de_intentos(
    client: TestClient, db: Session, crear_usuario
):
    # HU-03 / RNF-13: un login correcto reinicia los intentos fallidos consecutivos.
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="cuenta_reinicio")

    for _ in range(service.MAX_INTENTOS_FALLIDOS - 1):
        assert _login(client, usuario.nombre_usuario, "Otra12345").status_code == 401

    assert _login(client, usuario.nombre_usuario).status_code == 200
    db.refresh(usuario)
    assert usuario.intentos_fallidos == 0
    assert usuario.bloqueado_hasta is None

    for _ in range(service.MAX_INTENTOS_FALLIDOS - 1):
        assert _login(client, usuario.nombre_usuario, "Otra12345").status_code == 401

    # Si el contador no se hubiera reiniciado, este sería el sexto intento y daría 429.
    assert _login(client, usuario.nombre_usuario).status_code == 200


def test_sesion_vencida_por_inactividad_pide_iniciar_sesion(client: TestClient, crear_usuario):
    # HU-03 / RNF-14: tras el tiempo de inactividad, la siguiente petición responde 401.
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
    respuesta = client.get(ME, headers={"Cookie": f"{settings.cookie_name}={token}"})
    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == {
        "codigo": "no_autenticado",
        "mensaje": "Inicia sesión para continuar.",
    }


def test_asegurar_root_crea_un_solo_root(db: Session):
    # RF-01: tras la instalación existe exactamente un usuario root.
    assert service.asegurar_root(db, "root", "Clave1234") is True
    assert service.asegurar_root(db, "otro_root", "Clave5678") is False
    total = db.scalar(select(func.count()).select_from(Usuario).where(Usuario.rol == Rol.ROOT))
    assert total == 1
