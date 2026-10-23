"""HU-07, RF-08: ver y editar el perfil, con cambio de correo pendiente de verificación.

Cada test cita el criterio de aceptación que cubre.
"""

import hashlib
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.usuarios.models import TokenVerificacion, Usuario
from app.modules.usuarios.schemas import PerfilEntrada

REGISTRO = "/api/v1/usuarios/registro"
PERFIL = "/api/v1/usuarios/me/perfil"
VERIFICACION = "/api/v1/usuarios/verificacion"
REENVIAR = "/api/v1/usuarios/me/verificacion/reenviar"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"

MENSAJE_ENLACE_INVALIDO = "El enlace no es válido o venció. Pide uno nuevo."
MENSAJE_EMAIL_DUPLICADO = "Ese correo ya está registrado en otra cuenta."


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


def _entrada(**cambios: object) -> dict[str, object]:
    """Cuerpo de `PerfilEntrada`: los datos editables, sin documento ni usuario."""
    datos: dict[str, object] = {
        "nombres": "Laura",
        "apellidos": "Gómez Ríos",
        "fecha_nacimiento": "1995-03-14",
        "lugar_nacimiento": "Pereira, Risaralda",
        "direccion_facturacion": "Cra. 7 # 19-28, Pereira",
        "genero": "femenino",
        "email": "laura.gomez@correo.co",
        "telefono": "310 555 0192",
    }
    datos.update(cambios)
    return datos


def _registrar(client: TestClient, **cambios: object):
    client.cookies.clear()
    return client.post(REGISTRO, json=_datos(**cambios))


def _token_del_correo(texto: str) -> str:
    return texto.split("verificar-correo?token=")[1].split()[0]


def _usuario(db: Session, nombre_usuario: str = "lauragomez") -> Usuario:
    db.expire_all()
    usuario = db.scalar(select(Usuario).where(Usuario.nombre_usuario == nombre_usuario))
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


def _assert_error(respuesta, estado: int, codigo: str, mensaje: str, campos=None) -> None:
    assert respuesta.status_code == estado
    esperado = {"codigo": codigo, "mensaje": mensaje}
    if campos:
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


def test_perfil_actualizado_se_ve_al_volver_a_abrir(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-07 (AC1): al volver a abrir el perfil se ven los datos actualizados."""
    assert _registrar(client).status_code == 201

    respuesta = client.put(
        PERFIL,
        json=_entrada(
            nombres="Laura Sofía",
            apellidos="Gómez Ruiz",
            fecha_nacimiento="1996-04-15",
            lugar_nacimiento="Manizales, Caldas",
            direccion_facturacion="Calle 10 # 4-20, Manizales",
            genero="otro",
            telefono="320 555 0000",
        ),
    )

    assert respuesta.status_code == 200
    perfil = client.get(PERFIL).json()
    assert perfil["nombres"] == "Laura Sofía"
    assert perfil["apellidos"] == "Gómez Ruiz"
    assert perfil["fecha_nacimiento"] == "1996-04-15"
    assert perfil["lugar_nacimiento"] == "Manizales, Caldas"
    assert perfil["direccion_facturacion"] == "Calle 10 # 4-20, Manizales"
    assert perfil["genero"] == "otro"
    assert perfil["telefono"] == "320 555 0000"
    assert client.get(ME).json()["nombres"] == "Laura Sofía"

    usuario = _usuario(db)
    assert usuario.nombres == "Laura Sofía"
    assert usuario.lugar_nacimiento == "Manizales, Caldas"


def test_documento_y_nombre_usuario_solo_lectura(
    client: TestClient, correos: list[tuple[str, str, str, str | None]]
):
    """HU-07 (AC2): el documento y el nombre de usuario no están en PerfilEntrada."""
    assert _registrar(client).status_code == 201
    assert {"tipo_documento", "numero_documento", "nombre_usuario"}.isdisjoint(
        PerfilEntrada.model_fields
    )

    respuesta = client.put(
        PERFIL,
        json={
            **_entrada(),
            "tipo_documento": "PA",
            "numero_documento": "9999999999",
            "nombre_usuario": "otro",
        },
    )

    assert respuesta.status_code == 200
    perfil = client.get(PERFIL).json()
    assert perfil["tipo_documento"] == "CC"
    assert perfil["numero_documento"] == "1088345921"
    assert perfil["nombre_usuario"] == "lauragomez"


def test_cambio_de_correo_queda_pendiente_y_el_anterior_sigue_vigente(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-07 (AC3): el correo nuevo queda pendiente y el anterior sigue en la cuenta."""
    assert _registrar(client).status_code == 201
    assert (
        client.post(VERIFICACION, json={"token": _token_del_correo(correos[0][2])}).status_code
        == 204
    )

    respuesta = client.put(PERFIL, json=_entrada(email="laura.g@nuevo.co"))

    assert respuesta.status_code == 200
    perfil = respuesta.json()
    assert perfil["email"] == "laura.gomez@correo.co"
    assert perfil["email_pendiente"] == "laura.g@nuevo.co"
    assert perfil["email_verificado"] is True
    assert correos[-1][0] == "laura.g@nuevo.co"
    assert "nuevo correo" in correos[-1][1].lower()
    assert _usuario(db).email == "laura.gomez@correo.co"

    client.cookies.clear()
    assert (
        client.post(
            LOGIN, json={"usuario": "laura.gomez@correo.co", "contrasena": "Clave1234"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            LOGIN, json={"usuario": "laura.g@nuevo.co", "contrasena": "Clave1234"}
        ).status_code
        == 401
    )


def test_cambio_de_correo_de_punta_a_punta_con_el_token(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-07 (AC3): verificar el enlace del correo nuevo lo convierte en el de la cuenta."""
    assert _registrar(client).status_code == 201
    assert (
        client.post(VERIFICACION, json={"token": _token_del_correo(correos[0][2])}).status_code
        == 204
    )
    assert client.put(PERFIL, json=_entrada(email="laura.g@nuevo.co")).status_code == 200
    token = _token_del_correo(correos[1][2])

    respuesta = client.post(VERIFICACION, json={"token": token})

    assert respuesta.status_code == 204
    perfil = client.get(PERFIL).json()
    assert perfil["email"] == "laura.g@nuevo.co"
    assert perfil["email_pendiente"] is None
    assert perfil["email_verificado"] is True
    assert client.get(ME).json()["email"] == "laura.g@nuevo.co"
    assert _usuario(db).email == "laura.g@nuevo.co"
    assert _fila_del_token(db, token).usado_en is not None

    client.cookies.clear()
    assert (
        client.post(
            LOGIN, json={"usuario": "laura.gomez@correo.co", "contrasena": "Clave1234"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            LOGIN, json={"usuario": "laura.g@nuevo.co", "contrasena": "Clave1234"}
        ).status_code
        == 200
    )


def test_reenviar_verificacion_usa_el_correo_pendiente(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-07 + HU-02: el reenvío va al correo pendiente y invalida el enlace anterior."""
    assert _registrar(client).status_code == 201
    assert (
        client.post(VERIFICACION, json={"token": _token_del_correo(correos[0][2])}).status_code
        == 204
    )
    assert client.put(PERFIL, json=_entrada(email="laura.g@nuevo.co")).status_code == 200
    token_anterior = _token_del_correo(correos[1][2])

    respuesta = client.post(REENVIAR)

    assert respuesta.status_code == 204
    assert len(correos) == 3
    assert correos[2][0] == "laura.g@nuevo.co"
    assert _fila_del_token(db, token_anterior).usado_en is not None
    anterior = client.post(VERIFICACION, json={"token": token_anterior})
    _assert_error(anterior, 400, "enlace_invalido", MENSAJE_ENLACE_INVALIDO)


def test_correo_de_otra_cuenta_del_mismo_rol_es_rechazado(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]], crear_usuario
):
    """HU-07 (AC4): un correo que ya usa otra cuenta del mismo rol es rechazado."""
    crear_usuario(Rol.CLIENTE, nombre_usuario="otrocliente", email="otro@correo.co")
    assert _registrar(client).status_code == 201

    respuesta = client.put(PERFIL, json=_entrada(email="otro@correo.co"))

    _assert_error(
        respuesta,
        409,
        "datos_duplicados",
        "Alguno de los datos ya pertenece a otra cuenta.",
        {"email": MENSAJE_EMAIL_DUPLICADO},
    )
    perfil = client.get(PERFIL).json()
    assert perfil["email"] == "laura.gomez@correo.co"
    assert perfil["email_pendiente"] is None
    assert len(correos) == 1


def test_correo_pendiente_de_otra_cuenta_tambien_es_duplicado(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]], crear_usuario
):
    """HU-07 + RF-04: dos cuentas del mismo rol no pueden perseguir el mismo correo nuevo."""
    otro = crear_usuario(Rol.CLIENTE, nombre_usuario="otrocliente", email="otro@correo.co")
    otro.email_pendiente = "disputado@correo.co"
    db.commit()
    assert _registrar(client).status_code == 201

    respuesta = client.put(PERFIL, json=_entrada(email="disputado@correo.co"))

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["campos"]["email"] == MENSAJE_EMAIL_DUPLICADO


def test_un_correo_de_otro_rol_no_es_duplicado(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]], crear_usuario
):
    """HU-07 + SUP-18: cliente y administrador pueden compartir el mismo correo."""
    crear_usuario(Rol.ADMIN, nombre_usuario="admincompartido", email="compartido@correo.co")
    assert _registrar(client).status_code == 201

    respuesta = client.put(PERFIL, json=_entrada(email="compartido@correo.co"))

    assert respuesta.status_code == 200
    assert respuesta.json()["email_pendiente"] == "compartido@correo.co"


def test_root_no_tiene_perfil(client_como):
    """HU-07 (AC5): el root no tiene perfil y recibe 403 sin_permiso."""
    client = client_como(Rol.ROOT)

    consulta = client.get(PERFIL)
    actualizacion = client.put(PERFIL, json=_entrada())

    _assert_error(
        consulta,
        403,
        "sin_permiso",
        "Tu rol no tiene permiso para esta acción.",
    )
    _assert_error(
        actualizacion,
        403,
        "sin_permiso",
        "Tu rol no tiene permiso para esta acción.",
    )


def test_fecha_nacimiento_futura_es_rechazada(client: TestClient, correos):
    """HU-07 / RF-08: una fecha de nacimiento futura responde 422 datos_invalidos."""
    assert _registrar(client).status_code == 201
    manana = (date.today() + timedelta(days=1)).isoformat()

    respuesta = client.put(PERFIL, json=_entrada(fecha_nacimiento=manana))

    _assert_error(
        respuesta,
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        {"fecha_nacimiento": "La fecha de nacimiento no puede ser futura."},
    )


def test_guardar_sin_cambiar_el_correo_no_envia_enlace(client: TestClient, correos):
    """HU-07: guardar otros datos no reenvía el enlace del correo vigente ni del pendiente."""
    assert _registrar(client).status_code == 201

    assert client.put(PERFIL, json=_entrada(telefono="320 555 0000")).status_code == 200
    assert len(correos) == 1

    assert client.put(PERFIL, json=_entrada(email="laura.g@nuevo.co")).status_code == 200
    assert len(correos) == 2

    respuesta = client.put(PERFIL, json=_entrada(email="laura.g@nuevo.co", telefono="320 111 0000"))

    assert respuesta.status_code == 200
    assert respuesta.json()["email_pendiente"] == "laura.g@nuevo.co"
    assert len(correos) == 2


def test_volver_al_correo_vigente_descarta_el_pendiente(
    client: TestClient, db: Session, correos: list[tuple[str, str, str, str | None]]
):
    """HU-07: si el usuario vuelve a escribir su correo, se descarta el pendiente."""
    assert _registrar(client).status_code == 201
    assert client.put(PERFIL, json=_entrada(email="laura.g@nuevo.co")).status_code == 200
    token_pendiente = _token_del_correo(correos[1][2])

    respuesta = client.put(PERFIL, json=_entrada())

    assert respuesta.status_code == 200
    assert respuesta.json()["email_pendiente"] is None
    assert _fila_del_token(db, token_pendiente).usado_en is not None
    _assert_error(
        client.post(VERIFICACION, json={"token": token_pendiente}),
        400,
        "enlace_invalido",
        MENSAJE_ENLACE_INVALIDO,
    )


def test_correo_se_guarda_en_minusculas(client: TestClient, correos):
    """HU-07 / RF-04: el correo se normaliza a minúsculas antes de quedar pendiente."""
    assert _registrar(client).status_code == 201

    respuesta = client.put(PERFIL, json=_entrada(email="Nueva.Correo@Ejemplo.CO"))

    assert respuesta.status_code == 200
    assert respuesta.json()["email_pendiente"] == "nueva.correo@ejemplo.co"


def test_administrador_ve_y_edita_su_perfil(
    client: TestClient, db: Session, correos, crear_usuario
):
    """HU-07: un administrador con el registro completo también tiene perfil."""
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="adminperfil", email="admin@correo.co")
    admin.tipo_documento = "CC"
    admin.numero_documento = "80123456"
    admin.nombres = "Carlos"
    admin.apellidos = "Ruiz"
    admin.fecha_nacimiento = date(1988, 7, 2)
    admin.lugar_nacimiento = "Bogotá, Cundinamarca"
    admin.direccion_facturacion = "Calle 100 # 15-20, Bogotá"
    admin.genero = "masculino"
    admin.email_verificado = True
    db.commit()
    assert (
        client.post(LOGIN, json={"usuario": "adminperfil", "contrasena": "Clave1234"}).status_code
        == 200
    )

    perfil = client.get(PERFIL)
    assert perfil.status_code == 200
    assert perfil.json()["rol"] == "admin"
    assert perfil.json()["suscrito_noticias"] is False
    assert perfil.json()["imagen_url"] is None

    respuesta = client.put(PERFIL, json=_entrada(nombres="Carlos Andrés", email="admin@correo.co"))
    assert respuesta.status_code == 200
    assert client.get(PERFIL).json()["nombres"] == "Carlos Andrés"


def test_administrador_sin_registro_completo_no_tiene_perfil(client: TestClient, crear_usuario):
    """HU-07: un administrador sin datos personales todavía no tiene perfil."""
    crear_usuario(Rol.ADMIN, nombre_usuario="adminincompleto")
    assert (
        client.post(
            LOGIN, json={"usuario": "adminincompleto", "contrasena": "Clave1234"}
        ).status_code
        == 200
    )

    _assert_error(client.get(PERFIL), 404, "no_encontrado", "El recurso no existe.")
