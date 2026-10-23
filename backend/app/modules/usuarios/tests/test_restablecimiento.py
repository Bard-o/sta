"""HU-05, RF-07 y RNF-08: restablecimiento de contraseña con un enlace de un solo uso.

Cada test cita el criterio de aceptación que cubre.
"""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    MENSAJE_POLITICA_CONTRASENA,
    Rol,
    verificar_contrasena,
)
from app.core.testing import CONTRASENA_TEST
from app.modules.usuarios.models import TokenRestablecimiento, Usuario

SOLICITAR = "/api/v1/auth/restablecimiento"
CONFIRMAR = "/api/v1/auth/restablecimiento/confirmar"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
NUEVA = "OtraClave99"
MENSAJE_RESTABLECIMIENTO = (
    "Si el correo está registrado, recibirás un enlace válido por 30 minutos."
)
MENSAJE_ENLACE_INVALIDO = "El enlace no es válido o venció. Pide uno nuevo."
CORREO = "laura.gomez@correo.co"


def _solicitar(client: TestClient, email: str = CORREO):
    return client.post(SOLICITAR, json={"email": email})


def _confirmar(
    client: TestClient,
    token: str,
    *,
    nueva: str = NUEVA,
    confirmacion: str | None = None,
):
    return client.post(
        CONFIRMAR,
        json={
            "token": token,
            "contrasena_nueva": nueva,
            "confirmacion": nueva if confirmacion is None else confirmacion,
        },
    )


def _token_del_correo(texto: str) -> str:
    return texto.split("restablecer-contrasena?token=")[1].split()[0]


def _fila_del_token(db: Session, token: str) -> TokenRestablecimiento:
    fila = db.scalar(
        select(TokenRestablecimiento).where(
            TokenRestablecimiento.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    assert fila is not None
    return fila


def _assert_error(respuesta, estado: int, codigo: str, mensaje: str, campos=None) -> None:
    assert respuesta.status_code == estado
    esperado = {"codigo": codigo, "mensaje": mensaje}
    if campos is not None:
        esperado["campos"] = campos
    assert respuesta.json() == {"error": esperado}


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


def test_la_solicitud_responde_lo_mismo_con_correo_existente_e_inexistente(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-1 / RF-07: la respuesta es idéntica exista o no el correo."""
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez", email=CORREO)

    existente = _solicitar(client)
    inexistente = _solicitar(client, "nadie@correo.co")

    assert existente.status_code == inexistente.status_code == 202
    assert existente.json() == inexistente.json() == {"mensaje": MENSAJE_RESTABLECIMIENTO}
    assert "set-cookie" not in existente.headers
    assert "set-cookie" not in inexistente.headers
    # Solo la cuenta existente genera correo.
    assert len(correos) == 1
    assert correos[0][0] == CORREO
    filas = db.scalars(
        select(TokenRestablecimiento).where(TokenRestablecimiento.usuario_id == usuario.id)
    ).all()
    assert len(filas) == 1


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ADMIN], ids=lambda rol: rol.value)
def test_el_enlace_permite_definir_una_contrasena_nueva_valida(
    rol: Rol,
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-2 / RNF-08: cliente y administrador reciben un enlace que define una
    contraseña nueva que cumple la política."""
    usuario = crear_usuario(rol, nombre_usuario=f"{rol.value}_test", email=CORREO)

    assert _solicitar(client).status_code == 202
    assert len(correos) == 1
    destinatario, _, texto, html = correos[0]
    assert destinatario == CORREO
    assert "restablecer-contrasena?token=" in texto
    token = _token_del_correo(texto)
    assert token in html

    fila = _fila_del_token(db, token)
    assert fila.usado_en is None
    vigencia = fila.expira_en - datetime.now(UTC)
    assert timedelta(minutes=29) < vigencia <= timedelta(minutes=30)
    # El token en claro solo viaja en el correo.
    assert (
        db.scalar(select(TokenRestablecimiento).where(TokenRestablecimiento.token_hash == token))
        is None
    )

    respuesta = _confirmar(client, token)
    assert respuesta.status_code == 204, respuesta.text
    assert respuesta.content == b""

    db.refresh(usuario)
    assert usuario.password_hash.startswith("$argon2")
    assert verificar_contrasena(NUEVA, usuario.password_hash)
    assert not verificar_contrasena(CONTRASENA_TEST, usuario.password_hash)
    assert _fila_del_token(db, token).usado_en is not None

    anterior = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert anterior.status_code == 401
    nueva = client.post(LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": NUEVA})
    assert nueva.status_code == 200


def test_un_enlace_vencido_devuelve_enlace_invalido_y_permite_pedir_otro(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-3: un enlace vencido muestra el error y se puede solicitar otro.

    El reloj se controla moviendo `expira_en` al pasado en la base de datos, como en HU-02.
    """
    usuario = crear_usuario(Rol.CLIENTE, email=CORREO)
    assert _solicitar(client).status_code == 202
    vencido = _token_del_correo(correos[0][2])
    fila = _fila_del_token(db, vencido)
    fila.expira_en = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    respuesta = _confirmar(client, vencido)

    _assert_error(respuesta, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)
    db.refresh(usuario)
    assert verificar_contrasena(CONTRASENA_TEST, usuario.password_hash)

    # Se puede pedir uno nuevo y el enlace nuevo sí funciona.
    assert _solicitar(client).status_code == 202
    assert len(correos) == 2
    nuevo = _token_del_correo(correos[1][2])
    assert nuevo != vencido
    assert _confirmar(client, nuevo).status_code == 204
    db.refresh(usuario)
    assert verificar_contrasena(NUEVA, usuario.password_hash)


def test_un_enlace_ya_usado_devuelve_enlace_invalido(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-3: un enlace ya usado no se puede reutilizar."""
    usuario = crear_usuario(Rol.CLIENTE, email=CORREO)
    assert _solicitar(client).status_code == 202
    token = _token_del_correo(correos[0][2])
    assert _confirmar(client, token).status_code == 204
    db.refresh(usuario)
    hash_despues_del_uso = usuario.password_hash

    respuesta = _confirmar(client, token, nueva="TerceraClave77")

    _assert_error(respuesta, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)
    db.refresh(usuario)
    assert usuario.password_hash == hash_despues_del_uso


def test_restablecer_cierra_las_sesiones_y_la_contrasena_anterior_deja_de_funcionar(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-4 / RF-07: al restablecer se cierran todas las sesiones abiertas y la
    contraseña anterior deja de funcionar."""
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez", email=CORREO)
    assert (
        client.post(
            LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
        ).status_code
        == 200
    )
    version_antes = usuario.version_sesion
    assert client.get(ME).status_code == 200

    assert _solicitar(client).status_code == 202
    token = _token_del_correo(correos[0][2])
    assert _confirmar(client, token).status_code == 204

    # La cookie emitida antes del restablecimiento ya no sirve.
    assert client.get(ME).status_code == 401
    assert client.get(ME).json()["error"]["codigo"] == "no_autenticado"
    db.refresh(usuario)
    assert usuario.version_sesion == version_antes + 1

    anterior = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert anterior.status_code == 401
    assert anterior.json()["error"]["codigo"] == "credenciales_invalidas"
    nueva = client.post(LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": NUEVA})
    assert nueva.status_code == 200


def test_ni_las_respuestas_ni_el_correo_muestran_la_contrasena_actual(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-5 / RF-07: en ningún caso se muestra ni se envía la contraseña actual."""
    usuario = crear_usuario(Rol.CLIENTE, email=CORREO)

    solicitud = _solicitar(client)
    token = _token_del_correo(correos[0][2])
    confirmacion = _confirmar(client, token)

    assert CONTRASENA_TEST not in solicitud.text
    assert CONTRASENA_TEST not in confirmacion.text
    assert "password_hash" not in solicitud.text
    assert "password_hash" not in confirmacion.text
    destinatario, asunto, texto, html = correos[0]
    assert destinatario == CORREO
    for contenido in (asunto, texto, html or ""):
        assert CONTRASENA_TEST not in contenido
    db.refresh(usuario)
    assert usuario.password_hash != CONTRASENA_TEST


def test_un_correo_compartido_recibe_un_enlace_por_cuenta_y_el_root_ninguno(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-6 / SUP-18: si el correo pertenece a un cliente y a un administrador llega
    un enlace por cada cuenta; el root nunca recibe enlace."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="laura_cliente", email=CORREO)
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="laura_admin", email=CORREO)
    root = crear_usuario(Rol.ROOT, nombre_usuario="root_test", email=CORREO)

    assert _solicitar(client).status_code == 202

    assert len(correos) == 2  # nunca el root
    assert all(destinatario == CORREO for destinatario, *_ in correos)
    tokens = [_token_del_correo(correo[2]) for correo in correos]
    assert len(set(tokens)) == 2
    filas = [_fila_del_token(db, token) for token in tokens]
    assert {fila.usuario_id for fila in filas} == {cliente.id, admin.id}

    textos = [correo[2] for correo in correos]
    assert any("cuenta de cliente" in texto and "laura_cliente" in texto for texto in textos)
    assert any("cuenta de administrador" in texto and "laura_admin" in texto for texto in textos)

    hash_root_antes = root.password_hash
    for token in tokens:
        assert _confirmar(client, token).status_code == 204

    db.refresh(cliente)
    db.refresh(admin)
    db.refresh(root)
    assert verificar_contrasena(NUEVA, cliente.password_hash)
    assert verificar_contrasena(NUEVA, admin.password_hash)
    assert root.password_hash == hash_root_antes
    assert root.version_sesion == 0


def test_token_inexistente_devuelve_enlace_invalido(client: TestClient) -> None:
    """HU-05 CA-3: un token que no existe responde 400 enlace_invalido."""
    respuesta = _confirmar(client, "token-que-no-existe")

    _assert_error(respuesta, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)


@pytest.mark.parametrize(
    "nueva", ["Clave12", "12345678", "abcdefgh"], ids=["corta", "sin-letra", "sin-numero"]
)
def test_rechaza_contrasena_nueva_que_no_cumple_la_politica(
    nueva: str,
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-2 / RNF-08: la contraseña nueva necesita 8 caracteres, una letra y un número."""
    usuario = crear_usuario(Rol.CLIENTE, email=CORREO)
    assert _solicitar(client).status_code == 202
    token = _token_del_correo(correos[0][2])
    hash_antes = usuario.password_hash

    respuesta = _confirmar(client, token, nueva=nueva)

    _assert_error(
        respuesta,
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        {"contrasena_nueva": MENSAJE_POLITICA_CONTRASENA},
    )
    db.refresh(usuario)
    assert usuario.password_hash == hash_antes
    # El token sigue disponible para corregir la contraseña.
    assert _fila_del_token(db, token).usado_en is None
    assert _confirmar(client, token).status_code == 204


def test_rechaza_confirmacion_que_no_coincide(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 CA-2: la confirmación debe coincidir con la contraseña nueva."""
    usuario = crear_usuario(Rol.CLIENTE, email=CORREO)
    assert _solicitar(client).status_code == 202
    token = _token_del_correo(correos[0][2])
    hash_antes = usuario.password_hash

    respuesta = _confirmar(client, token, confirmacion="OtraClave98")

    _assert_error(
        respuesta,
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        {"confirmacion": "Las contraseñas no coinciden."},
    )
    db.refresh(usuario)
    assert usuario.password_hash == hash_antes
    assert _fila_del_token(db, token).usado_en is None


def test_confirmar_no_exige_sesion(
    client: TestClient,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05 / RF-07: el enlace se puede abrir en otro dispositivo, sin la cookie de sesión."""
    crear_usuario(Rol.CLIENTE, email=CORREO)
    assert _solicitar(client).status_code == 202
    token = _token_del_correo(correos[0][2])
    client.cookies.clear()

    respuesta = _confirmar(client, token)

    assert respuesta.status_code == 204
    assert "set-cookie" not in respuesta.headers


def test_solicitar_un_enlace_nuevo_invalida_el_anterior(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05: al pedir otro enlace, el anterior deja de servir."""
    crear_usuario(Rol.CLIENTE, email=CORREO)
    assert _solicitar(client).status_code == 202
    anterior = _token_del_correo(correos[0][2])

    assert _solicitar(client).status_code == 202
    nuevo = _token_del_correo(correos[1][2])

    assert nuevo != anterior
    assert _fila_del_token(db, anterior).usado_en is not None
    _assert_error(_confirmar(client, anterior), 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)
    assert _confirmar(client, nuevo).status_code == 204


def test_una_cuenta_inactiva_no_recibe_enlace_y_su_token_no_sirve(
    client: TestClient,
    db: Session,
    crear_usuario: Callable[..., Usuario],
    correos: list[tuple[str, str, str, str | None]],
) -> None:
    """HU-05: una cuenta desactivada no recibe enlace; si se desactiva después de pedirlo,
    el token deja de servir."""
    inactiva = crear_usuario(
        Rol.CLIENTE, nombre_usuario="inactiva", email="inactiva@correo.co", activo=False
    )
    assert _solicitar(client, "inactiva@correo.co").status_code == 202
    assert correos == []

    activa = crear_usuario(Rol.CLIENTE, nombre_usuario="activa", email=CORREO)
    assert _solicitar(client).status_code == 202
    token = _token_del_correo(correos[0][2])
    activa.activo = False
    db.commit()

    _assert_error(_confirmar(client, token), 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)
    db.refresh(inactiva)
    assert verificar_contrasena(CONTRASENA_TEST, inactiva.password_hash)


def test_la_solicitud_responde_202_si_el_correo_no_se_puede_enviar(
    client: TestClient,
    crear_usuario: Callable[..., Usuario],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-05 / RF-07: un fallo de SMTP no cambia la respuesta; queda en el log sin el correo."""

    def _falla(*_: object, **__: object) -> None:
        raise OSError("smtp no disponible")

    monkeypatch.setattr("app.modules.usuarios.service.enviar_correo", _falla)
    logger = Mock()
    monkeypatch.setattr("app.modules.usuarios.service.logger", logger)
    usuario = crear_usuario(Rol.CLIENTE, email=CORREO)

    respuesta = _solicitar(client)

    assert respuesta.status_code == 202
    assert respuesta.json() == {"mensaje": MENSAJE_RESTABLECIMIENTO}
    logger.exception.assert_called_once()
    argumentos = logger.exception.call_args.args
    assert usuario.id in argumentos
    assert not any(CORREO in str(argumento) for argumento in argumentos)
