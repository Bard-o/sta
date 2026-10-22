"""HU-01, RF-03, RF-04 y RF-05: registro de cliente con enlace de verificación.

Cada test cita el criterio de aceptación que cubre.
"""

import hashlib
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Rol
from app.modules.usuarios.models import TokenVerificacion, Usuario

REGISTRO = "/api/v1/usuarios/registro"


def _datos(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "tipo_documento": "CC",
        "numero_documento": "1088345921",
        "nombres": "Laura",
        "apellidos": "Gómez Ríos",
        "fecha_nacimiento": "1995-03-14",
        "lugar_nacimiento": "Pereira, Risaralda",
        "direccion_facturacion": "Cra. 7 # 19-28, Pereira",
        "genero": "femenino",
        "email": "laura.gomez@correo.co",
        "telefono": "310 555 0192",
        "nombre_usuario": "lauragomez",
        "contrasena": "Clave1234",
        "acepta_politica": True,
    }
    datos.update(cambios)
    return datos


def _registrar(client: TestClient, **cambios: object):
    """Registra desde un navegador sin sesión (el registro cierra sesión al terminar)."""
    client.cookies.clear()
    return client.post(REGISTRO, json=_datos(**cambios))


def _token_del_correo(texto: str) -> str:
    return texto.split("verificar-correo?token=")[1].split()[0]


@pytest.fixture(autouse=True)
def _sin_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ningún test de registro abre SMTP: el correo se captura o se descarta."""
    monkeypatch.setattr("app.modules.usuarios.service.enviar_correo", lambda *_, **__: None)


@pytest.fixture
def correos(
    monkeypatch: pytest.MonkeyPatch, _sin_smtp: None
) -> list[tuple[str, str, str, str | None]]:
    """Captura los correos enviados en vez de abrir SMTP."""
    enviados: list[tuple[str, str, str, str | None]] = []

    def _falso(destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
        enviados.append((destinatario, asunto, texto, html))

    monkeypatch.setattr("app.modules.usuarios.service.enviar_correo", _falso)
    return enviados


def test_registro_valido_crea_cuenta_inicia_sesion_y_devuelve_el_cliente(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-01 / RF-03: un registro con todos los datos válidos crea la cuenta, envía el
    enlace de verificación e inicia la sesión."""
    respuesta = _registrar(client)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre_usuario"] == "lauragomez"
    assert cuerpo["nombres"] == "Laura"
    assert cuerpo["apellidos"] == "Gómez Ríos"
    assert cuerpo["rol"] == "cliente"
    assert cuerpo["email"] == "laura.gomez@correo.co"
    assert cuerpo["email_verificado"] is False
    assert "password_hash" not in cuerpo

    set_cookie = respuesta.headers["set-cookie"]
    assert set_cookie.startswith(f"{get_settings().cookie_name}=")
    assert "HttpOnly" in set_cookie

    usuario = db.scalar(select(Usuario).where(Usuario.nombre_usuario == "lauragomez"))
    assert usuario is not None
    assert usuario.rol == Rol.CLIENTE
    assert usuario.tipo_documento == "CC"
    assert usuario.numero_documento == "1088345921"
    assert usuario.telefono == "310 555 0192"
    assert usuario.fecha_nacimiento == date(1995, 3, 14)
    assert usuario.fecha_aceptacion_politica is not None

    assert len(correos) == 1
    destinatario, _, texto, _ = correos[0]
    assert destinatario == "laura.gomez@correo.co"
    assert "verificar-correo?token=" in texto


def test_correo_de_verificacion_lleva_un_token_valido(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-01 / RF-05 / SUP-19: el enlace lleva un token de un solo uso que vence en 24 h."""
    assert _registrar(client).status_code == 201
    token = _token_del_correo(correos[0][2])

    fila = db.scalar(
        select(TokenVerificacion).where(
            TokenVerificacion.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    assert fila is not None
    assert fila.email == "laura.gomez@correo.co"
    assert fila.usado_en is None
    vigencia = fila.expira_en - datetime.now(UTC)
    assert timedelta(hours=23) < vigencia <= timedelta(hours=24)


def test_registro_responde_201_si_el_correo_no_se_puede_enviar(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """HU-01: un fallo de SMTP se registra en el log y no tumba el registro ya hecho."""

    def _falla(*_: object, **__: object) -> None:
        raise OSError("smtp no disponible")

    monkeypatch.setattr("app.modules.usuarios.service.enviar_correo", _falla)
    # Alembic desactiva los loggers existentes al migrar la base de tests, así que se espía
    # el logger del módulo en vez de capturar registros con caplog.
    logger = Mock()
    monkeypatch.setattr("app.modules.usuarios.service.logger", logger)

    respuesta = _registrar(client)

    assert respuesta.status_code == 201
    logger.exception.assert_called_once()


def test_registro_sin_aceptar_politica(client: TestClient, db: Session):
    """HU-01 / RF-03: el registro sin aceptar la política de datos es rechazado."""
    respuesta = _registrar(client, acepta_politica=False)

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "acepta_politica" in error["campos"]
    assert db.scalar(select(Usuario).where(Usuario.nombre_usuario == "lauragomez")) is None


def test_registro_con_fecha_nacimiento_futura(client: TestClient):
    """HU-01 / RF-03: una fecha de nacimiento futura se rechaza indicando el campo."""
    manana = (date.today() + timedelta(days=1)).isoformat()
    respuesta = _registrar(client, fecha_nacimiento=manana)

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "fecha_nacimiento" in error["campos"]


def test_registro_con_correo_mal_formado(client: TestClient):
    """HU-01 / RF-03: un correo mal formado se rechaza indicando el campo."""
    respuesta = _registrar(client, email="laura.gomez@correo")

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "email" in error["campos"]


@pytest.mark.parametrize(
    "contrasena", ["Clave12", "ClaveSegura", "12345678"], ids=["corta", "sin_numero", "sin_letra"]
)
def test_registro_con_contrasena_que_no_cumple_rnf_08(client: TestClient, contrasena: str):
    """HU-01 / RF-03 / RNF-08: la contraseña necesita 8 caracteres, una letra y un número."""
    respuesta = _registrar(client, contrasena=contrasena)

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "contrasena" in error["campos"]


def test_registro_con_documento_duplicado(client: TestClient):
    """HU-01 / RF-04: un documento que ya tiene otra cuenta de cliente se rechaza."""
    assert _registrar(client).status_code == 201
    respuesta = _registrar(client, email="otra@correo.co", nombre_usuario="otracuenta")

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "numero_documento" in error["campos"]


def test_registro_con_correo_duplicado(client: TestClient):
    """HU-01 / RF-04: un correo que ya tiene otra cuenta de cliente se rechaza."""
    assert _registrar(client).status_code == 201
    respuesta = _registrar(client, numero_documento="9999999", nombre_usuario="otracuenta")

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "email" in error["campos"]


def test_registro_con_nombre_usuario_duplicado_sin_importar_mayusculas(client: TestClient):
    """HU-01 / RF-04: el nombre de usuario es único en todo el sistema, sin distinguir
    mayúsculas."""
    assert _registrar(client).status_code == 201
    respuesta = _registrar(client, email="otra@correo.co", nombre_usuario="LauraGomez")

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "nombre_usuario" in error["campos"]


def test_registro_con_el_nombre_usuario_de_un_administrador(client: TestClient, crear_usuario):
    """HU-01 / RF-04: el nombre de usuario también es único frente a otras cuentas."""
    crear_usuario(Rol.ADMIN, nombre_usuario="lauragomez")
    respuesta = _registrar(client)

    assert respuesta.status_code == 409
    assert "nombre_usuario" in respuesta.json()["error"]["campos"]


def test_un_administrador_puede_tener_su_cuenta_de_cliente(
    client: TestClient, db: Session, crear_usuario
):
    """HU-01 / RF-04 / SUP-18: documento y correo son únicos dentro de cada rol, así que un
    administrador puede registrarse como cliente con los mismos datos."""
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="amejia", email="laura.gomez@correo.co")
    admin.tipo_documento = "CC"
    admin.numero_documento = "1088345921"
    db.commit()

    respuesta = _registrar(client)

    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == "cliente"


def test_menor_de_edad_puede_registrarse(client: TestClient):
    """HU-01 / RF-03: no hay edad mínima de registro (la restricción aplica al volar)."""
    respuesta = _registrar(client, fecha_nacimiento="2015-03-14")

    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == "cliente"


@pytest.mark.parametrize("rol", list(Rol), ids=lambda rol: rol.value)
def test_registro_con_sesion_abierta_responde_403(
    rol: Rol, client_como: Callable[[Rol], TestClient]
):
    """HU-01 / Apéndice B: con una sesión abierta el registro responde 403 sin_permiso."""
    cliente_http = client_como(rol)

    respuesta = cliente_http.post(REGISTRO, json=_datos())

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "sin_permiso"
