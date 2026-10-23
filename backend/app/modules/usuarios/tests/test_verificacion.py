"""HU-02, RF-05 y SUP-19: verificación del correo y reenvío del enlace.

Cada test cita el criterio de aceptación que cubre.
"""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.usuarios.models import TokenVerificacion, Usuario

REGISTRO = "/api/v1/usuarios/registro"
VERIFICACION = "/api/v1/usuarios/verificacion"
REENVIAR = "/api/v1/usuarios/me/verificacion/reenviar"
ME = "/api/v1/auth/me"

MENSAJE_ENLACE_INVALIDO = "El enlace no es válido o venció. Pide uno nuevo."
MENSAJE_CORREO_YA_VERIFICADO = "Tu correo ya está verificado."


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
    """Registra desde un navegador sin sesión: limpia la cookie de un registro anterior."""
    client.cookies.clear()
    return client.post(REGISTRO, json=_datos(**cambios))


def _token_del_correo(texto: str) -> str:
    return texto.split("verificar-correo?token=")[1].split()[0]


def _usuario(db: Session) -> Usuario:
    usuario = db.scalar(select(Usuario).where(Usuario.nombre_usuario == "lauragomez"))
    assert usuario is not None
    return usuario


def _fila_del_token(db: Session, token: str) -> TokenVerificacion:
    fila = db.scalar(
        select(TokenVerificacion).where(
            TokenVerificacion.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    assert fila is not None
    return fila


def _verificar(client: TestClient, token: str):
    return client.post(VERIFICACION, json={"token": token})


def _assert_error(respuesta, estado: int, codigo: str, mensaje: str) -> None:
    assert respuesta.status_code == estado
    assert respuesta.json() == {"error": {"codigo": codigo, "mensaje": mensaje}}


@pytest.fixture(autouse=True)
def _sin_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ningún test abre SMTP: el correo se captura o se descarta."""
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


def test_enlace_vigente_verifica_el_correo(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-02 (AC1): abrir un enlace vigente marca el correo como verificado."""
    assert _registrar(client).status_code == 201
    token = _token_del_correo(correos[0][2])

    respuesta = _verificar(client, token)

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert _fila_del_token(db, token).usado_en is not None
    assert _usuario(db).email_verificado is True
    assert client.get(ME).json()["email_verificado"] is True


def test_enlace_vigente_no_exige_sesion(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-02: el enlace se puede abrir en otro dispositivo, sin la cookie de sesión."""
    assert _registrar(client).status_code == 201
    token = _token_del_correo(correos[0][2])
    client.cookies.clear()

    respuesta = _verificar(client, token)

    assert respuesta.status_code == 204
    assert "set-cookie" not in respuesta.headers
    assert _usuario(db).email_verificado is True


def test_enlace_vencido_devuelve_enlace_invalido(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-02 (AC2): un enlace vencido responde 400 enlace_invalido.

    El reloj se controla moviendo `expira_en` al pasado en la base de datos, porque el
    proyecto no depende de una librería de reloj congelado.
    """
    assert _registrar(client).status_code == 201
    token = _token_del_correo(correos[0][2])
    fila = _fila_del_token(db, token)
    fila.expira_en = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    respuesta = _verificar(client, token)

    _assert_error(respuesta, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)
    assert _usuario(db).email_verificado is False


def test_enlace_ya_usado_devuelve_enlace_invalido(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-02 (AC2): un enlace ya usado responde 400 enlace_invalido."""
    assert _registrar(client).status_code == 201
    token = _token_del_correo(correos[0][2])
    assert _verificar(client, token).status_code == 204

    respuesta = _verificar(client, token)

    _assert_error(respuesta, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)
    assert _usuario(db).email_verificado is True


def test_token_inexistente_devuelve_enlace_invalido(client: TestClient):
    """HU-02 (AC2): un token que no existe responde 400 enlace_invalido."""
    respuesta = _verificar(client, "token-que-no-existe")

    _assert_error(respuesta, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)


def test_reenviar_envia_un_enlace_nuevo_e_invalida_el_anterior(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-02 (AC3): al reenviar, el enlace anterior deja de funcionar."""
    assert _registrar(client).status_code == 201
    token_anterior = _token_del_correo(correos[0][2])

    respuesta = client.post(REENVIAR)

    assert respuesta.status_code == 204
    assert len(correos) == 2
    token_nuevo = _token_del_correo(correos[1][2])
    assert token_nuevo != token_anterior
    assert _fila_del_token(db, token_anterior).usado_en is not None
    assert _fila_del_token(db, token_nuevo).usado_en is None

    anterior = _verificar(client, token_anterior)
    _assert_error(anterior, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)
    assert _verificar(client, token_nuevo).status_code == 204


def test_cliente_sin_verificar_pasa_a_verificado(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-02 (AC4): el flag que habilita reservar y comprar pasa de false a true.

    Reservar y comprar llegan en la iteración 2; suscribirse lo implementa HU-08. Aquí se
    prueba el estado `email_verificado` que ambos consultan.
    """
    assert _registrar(client).status_code == 201
    assert client.get(ME).json()["email_verificado"] is False
    token = _token_del_correo(correos[0][2])

    assert _verificar(client, token).status_code == 204

    assert client.get(ME).json()["email_verificado"] is True
    assert _usuario(db).email_verificado is True


def test_reenviar_sin_correo_pendiente_devuelve_correo_ya_verificado(
    client: TestClient, correos: list[tuple[str, str, str, str | None]]
):
    """HU-02 (AC5): reenviar sin un correo pendiente responde 409 correo_ya_verificado."""
    assert _registrar(client).status_code == 201
    token = _token_del_correo(correos[0][2])
    assert _verificar(client, token).status_code == 204

    respuesta = client.post(REENVIAR)

    _assert_error(respuesta, 409, "correo_ya_verificado", MENSAJE_CORREO_YA_VERIFICADO)


def test_reenviar_sin_correo_no_rompe(client_como: Callable[[Rol], TestClient]):
    """HU-02 (AC5): una cuenta sin correo no tiene nada pendiente que reenviar."""
    client = client_como(Rol.CLIENTE)

    respuesta = client.post(REENVIAR)

    _assert_error(respuesta, 409, "correo_ya_verificado", MENSAJE_CORREO_YA_VERIFICADO)
