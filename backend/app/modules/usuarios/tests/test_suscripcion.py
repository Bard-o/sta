"""HU-08, RF-09 y RF-56: suscripción a noticias y baja por enlace.

Cada test cita el criterio de aceptación que cubre. El envío del correo dentro de los 5
minutos posteriores a la publicación es del issue #32 (noticias); aquí se prueba la lista de
destinatarios, el cambio de estado y la baja sin sesión.
"""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.usuarios import service
from app.modules.usuarios.models import Usuario

SUSCRIPCION = "/api/v1/usuarios/me/suscripcion"
BAJA = "/api/v1/usuarios/suscripcion/baja"
LOGIN = "/api/v1/auth/login"

MENSAJE_CORREO_NO_VERIFICADO = "Verifica tu correo para suscribirte a noticias."
MENSAJE_ENLACE_INVALIDO = "El enlace no es válido o venció. Pide uno nuevo."


def _cliente(
    db: Session,
    crear_usuario: Callable[..., Any],
    *,
    nombre_usuario: str = "lauragomez",
    email: str = "laura@example.com",
    verificado: bool = True,
    activo: bool = True,
    rol: Rol = Rol.CLIENTE,
) -> Usuario:
    usuario = crear_usuario(rol, nombre_usuario=nombre_usuario, email=email, activo=activo)
    usuario.email_verificado = verificado
    usuario.nombres = "Laura"
    db.commit()
    return usuario


def _iniciar_sesion(client: TestClient, usuario: Usuario) -> None:
    respuesta = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert respuesta.status_code == 200, respuesta.text


def _suscripcion_de(usuario: Usuario, db: Session) -> Usuario:
    """Recarga el usuario para leer el estado que quedó guardado."""
    db.expire_all()
    guardado = db.get(Usuario, usuario.id)
    assert guardado is not None
    return guardado


def _assert_error(respuesta, estado: int, codigo: str, mensaje: str, campos=None) -> None:
    assert respuesta.status_code == estado
    esperado = {"codigo": codigo, "mensaje": mensaje}
    if campos is not None:
        esperado["campos"] = campos
    assert respuesta.json() == {"error": esperado}


def test_cliente_suscrito_aparece_como_destinatario_del_correo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # HU-08 CA-1 / RF-56: noticias obtiene como destinatario al cliente suscrito, con su
    # token de baja. El envío en ≤ 5 minutos lo cubre el issue #32.
    usuario = _cliente(db, crear_usuario)
    service.cambiar_suscripcion(db, usuario.id, noticias=True)

    destinatarios = service.suscriptores_noticias(db)

    assert len(destinatarios) == 1
    destinatario = destinatarios[0]
    assert destinatario.usuario_id == usuario.id
    assert destinatario.email == "laura@example.com"
    assert destinatario.nombres == "Laura"
    assert destinatario.token_baja

    # El token no vence ni cambia entre envíos: la siguiente consulta trae el mismo.
    assert service.suscriptores_noticias(db)[0].token_baja == destinatario.token_baja


def test_suscriptores_excluye_no_suscritos_inactivos_y_sin_verificar(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # HU-08 CA-2 / RF-56: solo reciben el correo los clientes activos, verificados y
    # suscritos. Un cliente no suscrito, inactivo, sin verificar o de otro rol queda fuera.
    suscrito = _cliente(db, crear_usuario, nombre_usuario="suscrito", email="suscrito@example.com")
    service.cambiar_suscripcion(db, suscrito.id, noticias=True)

    _cliente(db, crear_usuario, nombre_usuario="nosuscrito", email="nosuscrito@example.com")

    inactivo = _cliente(db, crear_usuario, nombre_usuario="inactivo", email="inactivo@example.com")
    service.cambiar_suscripcion(db, inactivo.id, noticias=True)
    inactivo.activo = False
    db.commit()

    _cliente(
        db,
        crear_usuario,
        nombre_usuario="sinverificar",
        email="sinverificar@example.com",
        verificado=False,
    )

    admin = _cliente(
        db,
        crear_usuario,
        nombre_usuario="admin_suscrito",
        email="admin@example.com",
        rol=Rol.ADMIN,
    )
    admin.suscrito_noticias = True
    admin.token_baja = "token-de-administrador"
    db.commit()

    destinatarios = service.suscriptores_noticias(db)

    assert [destinatario.usuario_id for destinatario in destinatarios] == [suscrito.id]


def test_baja_con_token_funciona_sin_sesion(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # HU-08 CA-3: el enlace «cancelar suscripción» del correo da de baja sin iniciar sesión.
    usuario = _cliente(db, crear_usuario)
    _iniciar_sesion(client, usuario)
    assert client.put(SUSCRIPCION, json={"noticias": True}).status_code == 200
    token = _suscripcion_de(usuario, db).token_baja
    assert token is not None

    client.cookies.clear()
    respuesta = client.post(BAJA, json={"token": token})

    assert respuesta.status_code == 204, respuesta.text
    assert _suscripcion_de(usuario, db).suscrito_noticias is False
    assert service.suscriptores_noticias(db) == []


def test_baja_con_token_inexistente_responde_enlace_invalido(
    client: TestClient,
) -> None:
    # HU-08 CA-3: un token que no corresponde a ninguna suscripción no da de baja a nadie.
    respuesta = client.post(BAJA, json={"token": "no-existe"})

    _assert_error(respuesta, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)


def test_baja_es_idempotente_con_el_mismo_token(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # Contrato HU-08: el token no vence; abrir dos veces el mismo enlace no muestra error.
    usuario = _cliente(db, crear_usuario)
    service.cambiar_suscripcion(db, usuario.id, noticias=True)
    token = _suscripcion_de(usuario, db).token_baja
    assert token is not None

    assert client.post(BAJA, json={"token": token}).status_code == 204
    assert client.post(BAJA, json={"token": token}).status_code == 204


def test_cliente_sin_correo_verificado_no_puede_suscribirse(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # HU-08 CA-4: sin el correo verificado no se puede suscribir. El frontend usa el código
    # para ofrecer el reenvío de la verificación.
    usuario = _cliente(db, crear_usuario, verificado=False)
    _iniciar_sesion(client, usuario)

    respuesta = client.put(SUSCRIPCION, json={"noticias": True})

    _assert_error(respuesta, 403, "correo_no_verificado", MENSAJE_CORREO_NO_VERIFICADO)
    assert _suscripcion_de(usuario, db).suscrito_noticias is False
    assert _suscripcion_de(usuario, db).token_baja is None

    # Tras verificar el correo, la suscripción ya se permite.
    usuario.email_verificado = True
    db.commit()
    assert client.put(SUSCRIPCION, json={"noticias": True}).json() == {"noticias": True}


def test_cliente_verificado_se_suscribe_con_efecto_inmediato(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # RF-09: el cambio de estado es inmediato y se refleja en el siguiente envío.
    usuario = _cliente(db, crear_usuario)
    _iniciar_sesion(client, usuario)

    respuesta = client.put(SUSCRIPCION, json={"noticias": True})

    assert respuesta.status_code == 200
    assert respuesta.json() == {"noticias": True}
    guardado = _suscripcion_de(usuario, db)
    assert guardado.suscrito_noticias is True
    assert guardado.token_baja
    assert [destinatario.usuario_id for destinatario in service.suscriptores_noticias(db)] == [
        usuario.id
    ]


def test_darse_de_baja_se_permite_sin_correo_verificado(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # Contrato HU-08: darse de baja siempre se permite, aunque el correo no esté verificado.
    usuario = _cliente(db, crear_usuario, verificado=False)
    _iniciar_sesion(client, usuario)

    respuesta = client.put(SUSCRIPCION, json={"noticias": False})

    assert respuesta.status_code == 200
    assert respuesta.json() == {"noticias": False}


def test_suscripcion_es_idempotente_y_conserva_el_token(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # HU-08 / RF-09: repetir la suscripción no rota el token, así que los enlaces de correos
    # anteriores siguen sirviendo.
    usuario = _cliente(db, crear_usuario)
    _iniciar_sesion(client, usuario)

    assert client.put(SUSCRIPCION, json={"noticias": True}).status_code == 200
    token = _suscripcion_de(usuario, db).token_baja
    assert client.put(SUSCRIPCION, json={"noticias": True}).status_code == 200

    guardado = _suscripcion_de(usuario, db)
    assert guardado.suscrito_noticias is True
    assert guardado.token_baja == token


def test_suscripcion_sin_el_campo_noticias_responde_422_datos_invalidos(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    # IU-07: el error de validación viaja en el formato único con el campo que falla.
    usuario = _cliente(db, crear_usuario)
    _iniciar_sesion(client, usuario)

    respuesta = client.put(SUSCRIPCION, json={})

    _assert_error(
        respuesta,
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        {"noticias": "Este campo es obligatorio."},
    )
