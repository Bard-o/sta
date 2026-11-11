"""HU-12, RF-02 a RF-04 y SUP-18: el administrador completa su registro con la invitación.

Cada test cita el criterio de aceptación que cubre.
"""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import MENSAJE_POLITICA_CONTRASENA, Rol, verificar_contrasena
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.usuarios import service
from app.modules.usuarios.models import TokenInvitacion, Usuario

RUTA = "/api/v1/administradores"
VALIDAR = f"{RUTA}/invitacion/validar"
COMPLETAR = f"{RUTA}/invitacion/completar"
LOGIN = "/api/v1/auth/login"
CONTRASENA_NUEVA = "MiClave2026"
ENLACE_INVALIDO = "El enlace no es válido o venció. Pide al root una invitación nueva."


def _datos_invitacion(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "nombre_usuario": "jtorres",
        "email": "jorge.torres@avianco.test",
    }
    datos.update(cambios)
    return datos


def _datos_completar(token: str, **cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "token": token,
        "tipo_documento": "CC",
        "numero_documento": "10234567",
        "nombres": "Jorge",
        "apellidos": "Torres",
        "fecha_nacimiento": "1990-05-02",
        "lugar_nacimiento": "Cali, Valle del Cauca",
        "direccion_facturacion": "Cl. 5 # 38-14, Cali",
        "genero": "masculino",
        "telefono": None,
        "contrasena": CONTRASENA_NUEVA,
        "confirmacion": CONTRASENA_NUEVA,
    }
    datos.update(cambios)
    return datos


def _datos_cliente(**cambios: object) -> dict[str, object]:
    """Los mismos datos personales del administrador, con otro nombre de usuario (SUP-18)."""
    datos: dict[str, object] = {
        "tipo_documento": "CC",
        "numero_documento": "10234567",
        "nombres": "Jorge",
        "apellidos": "Torres",
        "fecha_nacimiento": "1990-05-02",
        "lugar_nacimiento": "Cali, Valle del Cauca",
        "direccion_facturacion": "Cl. 5 # 38-14, Cali",
        "genero": "masculino",
        "email": "jorge.torres@avianco.test",
        "telefono": None,
        "nombre_usuario": "jorgecliente",
        "contrasena": "OtraClave99",
        "acepta_politica": True,
    }
    datos.update(cambios)
    return datos


def _token_de_correo(mensaje: EmailMessage) -> str:
    for parte in mensaje.walk():
        if parte.get_content_type() in ("text/plain", "text/html"):
            coincidencia = re.search(r"token=([A-Za-z0-9_-]+)", parte.get_content())
            if coincidencia:
                return coincidencia.group(1)
    raise AssertionError("El correo no trae el enlace de completar registro")


def _invitar(
    root: TestClient,
    smtp_falso: Any,
    **cambios: object,
) -> tuple[int, str]:
    """Invita a un administrador por la API y devuelve su id y el token del correo."""
    respuesta = root.post(RUTA, json=_datos_invitacion(**cambios))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"], _token_de_correo(smtp_falso.enviados[-1])


def _login(client: TestClient, nombre_usuario: str, contrasena: str) -> Any:
    return client.post(LOGIN, json={"usuario": nombre_usuario, "contrasena": contrasena})


# ---------- Criterio: el enlace se valida sin consumirlo ----------


def test_validar_invitacion_muestra_usuario_y_correo_sin_consumirla(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-12: el formulario conoce el usuario y el correo antes de pedir los datos."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)

    primera = root.post(VALIDAR, json={"token": token})
    segunda = root.post(VALIDAR, json={"token": token})

    assert primera.status_code == 200
    assert primera.json()["nombre_usuario"] == "jtorres"
    assert primera.json()["email"] == "jorge.torres@avianco.test"
    assert primera.json()["expira_en"] > datetime.now(UTC).isoformat()
    assert segunda.status_code == 200


def test_token_inexistente_responde_400_con_el_mensaje_de_la_hu(
    client: TestClient,
) -> None:
    """HU-12: el mensaje del enlace inválido es exacto y usa el formato único de error."""
    for ruta in (VALIDAR, COMPLETAR):
        respuesta = client.post(ruta, json={"token": "no-existe"})
        assert respuesta.status_code in (400, 422)
        if respuesta.status_code == 400:
            assert respuesta.json() == {
                "error": {"codigo": "enlace_invalido", "mensaje": ENLACE_INVALIDO}
            }


def test_una_invitacion_vencida_no_se_puede_validar_ni_completar(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any, db: Session
) -> None:
    """HU-12 · SUP-17: a las 72 horas el enlace deja de servir."""
    root = client_como(Rol.ROOT)
    admin_id, token = _invitar(root, smtp_falso)
    invitacion = db.scalars(
        select(TokenInvitacion).where(TokenInvitacion.usuario_id == admin_id)
    ).one()
    invitacion.expira_en = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    validar = root.post(VALIDAR, json={"token": token})
    completar = root.post(COMPLETAR, json=_datos_completar(token))

    for respuesta in (validar, completar):
        assert respuesta.status_code == 400
        assert respuesta.json() == {
            "error": {"codigo": "enlace_invalido", "mensaje": ENLACE_INVALIDO}
        }


# ---------- Criterio: completar el registro ----------


def test_completar_invitacion_guarda_los_datos_y_abre_la_sesion(
    client: TestClient,
    client_como: Callable[[Rol], TestClient],
    smtp_falso: Any,
    db: Session,
) -> None:
    """HU-12 CA-2: la sesión queda abierta y el administrador ya usa el resto de la API."""
    root = client_como(Rol.ROOT)
    admin_id, token = _invitar(root, smtp_falso)

    respuesta = client.post(COMPLETAR, json=_datos_completar(token))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == admin_id
    assert cuerpo["registro_completo"] is True
    assert cuerpo["email"] == "jorge.torres@avianco.test"
    assert cuerpo["email_verificado"] is True
    assert cuerpo["nombres"] == "Jorge"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["registro_completo"] is True
    assert me.json()["nombres"] == "Jorge"
    assert client.get("/api/v1/vuelos").status_code == 200

    perfil = client.get("/api/v1/usuarios/me/perfil")
    assert perfil.status_code == 200
    assert perfil.json()["numero_documento"] == "10234567"

    administrador = db.get(Usuario, admin_id)
    assert administrador is not None
    assert administrador.password_hash is not None
    assert administrador.password_hash.startswith("$argon2")
    assert verificar_contrasena(CONTRASENA_NUEVA, administrador.password_hash)
    assert administrador.email_pendiente is None
    invitacion = db.scalars(
        select(TokenInvitacion).where(TokenInvitacion.usuario_id == admin_id)
    ).one()
    assert invitacion.usado_en is not None


def test_con_la_contrasena_nueva_se_inicia_sesion_y_la_anterior_no_sirve(
    client: TestClient, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-12 CA-2: no existe contraseña temporal; la única válida es la que se define aquí."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)
    assert client.post(COMPLETAR, json=_datos_completar(token)).status_code == 200

    client.cookies.clear()
    vieja = _login(client, "jtorres", "Cualquiera123")
    assert vieja.status_code == 401
    assert vieja.json()["error"]["codigo"] == "credenciales_invalidas"

    nueva = _login(client, "jtorres", CONTRASENA_NUEVA)
    assert nueva.status_code == 200
    assert nueva.json()["registro_completo"] is True


def test_el_correo_del_administrador_se_toma_de_la_invitacion(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any, db: Session
) -> None:
    """HU-12: el correo ya viene del enlace y se guarda normalizado y verificado."""
    root = client_como(Rol.ROOT)
    admin_id, token = _invitar(root, smtp_falso, email="Jorge.Torres@AVIANCO.TEST")

    respuesta = root.post(COMPLETAR, json=_datos_completar(token, email="otro@avianco.test"))

    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "jorge.torres@avianco.test"
    assert respuesta.json()["email_verificado"] is True
    administrador = db.get(Usuario, admin_id)
    assert administrador is not None
    assert administrador.email == "jorge.torres@avianco.test"
    assert administrador.email_pendiente is None


def test_completar_dos_veces_o_con_un_token_usado_responde_400(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any, db: Session
) -> None:
    """HU-12 CA-5: el enlace es de un solo uso; no se puede reutilizar."""
    root = client_como(Rol.ROOT)
    admin_id, token = _invitar(root, smtp_falso)
    assert root.post(COMPLETAR, json=_datos_completar(token)).status_code == 200

    respuesta = root.post(COMPLETAR, json=_datos_completar(token, nombres="Otro"))

    assert respuesta.status_code == 400
    assert respuesta.json() == {"error": {"codigo": "enlace_invalido", "mensaje": ENLACE_INVALIDO}}
    administrador = db.get(Usuario, admin_id)
    assert administrador is not None
    assert administrador.nombres == "Jorge"


# ---------- Criterio: correo y documento únicos entre administradores ----------


def test_el_documento_es_unico_entre_administradores(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-12 CA-4 · RF-04: un documento que ya tiene otro administrador es rechazado."""
    root = client_como(Rol.ROOT)
    _, primer_token = _invitar(root, smtp_falso)
    _, segundo_token = _invitar(
        root, smtp_falso, nombre_usuario="atorres", email="ana.torres@avianco.test"
    )
    assert root.post(COMPLETAR, json=_datos_completar(primer_token)).status_code == 200

    respuesta = root.post(COMPLETAR, json=_datos_completar(segundo_token, nombres="Ana"))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "numero_documento" in error["campos"]


def test_el_correo_es_unico_entre_administradores(
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
    db: Session,
) -> None:
    """HU-12 CA-4 · RF-04: un correo que ya tiene otro administrador es rechazado."""
    root = client_como(Rol.ROOT)
    admin_id, token = _invitar(root, smtp_falso)
    invitado = db.get(Usuario, admin_id)
    assert invitado is not None
    # El correo está reservado por la invitación. Otro administrador lo toma después y el
    # token queda apuntando a un correo ya ocupado.
    invitado.email = None
    db.commit()
    ocupado = crear_usuario(
        Rol.ADMIN, nombre_usuario="otro_admin", email="jorge.torres@avianco.test"
    )

    respuesta = root.post(COMPLETAR, json=_datos_completar(token))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "email" in error["campos"]
    assert ocupado.email == "jorge.torres@avianco.test"


def test_el_correo_pendiente_de_otro_administrador_tambien_se_rechaza(
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
    db: Session,
) -> None:
    """HU-12 · RF-04, HU-07: no se ocupa un correo que otro administrador espera verificar."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)
    otro = crear_usuario(Rol.ADMIN, nombre_usuario="otro_admin", email="ocupado@avianco.test")
    otro.email_pendiente = "jorge.torres@avianco.test"
    db.commit()

    respuesta = root.post(COMPLETAR, json=_datos_completar(token))

    assert respuesta.status_code == 409
    assert "email" in respuesta.json()["error"]["campos"]


def test_el_administrador_puede_registrarse_como_cliente_con_los_mismos_datos(
    client: TestClient,
    client_como: Callable[[Rol], TestClient],
    smtp_falso: Any,
    db: Session,
) -> None:
    """HU-12 CA-3 · SUP-18: documento y correo se repiten entre roles, no dentro del rol."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)
    assert root.post(COMPLETAR, json=_datos_completar(token)).status_code == 200

    client.cookies.clear()  # el registro de clientes es solo para visitantes
    respuesta = client.post("/api/v1/usuarios/registro", json=_datos_cliente())

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["rol"] == "cliente"
    cliente = db.scalar(
        select(Usuario).where(
            Usuario.rol == Rol.CLIENTE, Usuario.email == "jorge.torres@avianco.test"
        )
    )
    assert cliente is not None
    assert cliente.numero_documento == "10234567"


# ---------- Casos de borde del formulario ----------


def test_fecha_nacimiento_futura_responde_422(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-12 · RF-03: la fecha de nacimiento no puede ser futura."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)
    manana = (date.today() + timedelta(days=1)).isoformat()

    respuesta = root.post(COMPLETAR, json=_datos_completar(token, fecha_nacimiento=manana))

    assert respuesta.status_code == 422
    assert "fecha_nacimiento" in respuesta.json()["error"]["campos"]


@pytest.fixture
def hoy_fijo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Congela el reloj del módulo el 03/11/2026 10:00 en Colombia (15:00 UTC)."""
    monkeypatch.setattr(service, "_ahora_utc", lambda: datetime(2026, 11, 3, 15, 0, tzinfo=UTC))


def test_fecha_nacimiento_de_mas_de_120_anos_responde_422(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any, hoy_fijo: None
) -> None:
    """HU-12 · RF-03 · SUP-43: con 120 años y un día se rechaza."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)

    respuesta = root.post(COMPLETAR, json=_datos_completar(token, fecha_nacimiento="1906-11-02"))

    assert respuesta.status_code == 422
    campo = respuesta.json()["error"]["campos"]["fecha_nacimiento"]
    assert campo == "Revisa la fecha: la edad máxima es 120 años."


def test_fecha_nacimiento_de_exactamente_120_anos_completa_el_registro(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any, hoy_fijo: None
) -> None:
    """HU-12 · RF-03 · SUP-43: quien cumple 120 años hoy puede completar su registro."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)

    respuesta = root.post(COMPLETAR, json=_datos_completar(token, fecha_nacimiento="1906-11-03"))

    assert respuesta.status_code == 200
    assert respuesta.json()["registro_completo"] is True


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"contrasena": "corta1", "confirmacion": "corta1"}, "contrasena"),
        ({"contrasena": "12345678", "confirmacion": "12345678"}, "contrasena"),
        ({"contrasena": "Nueva 2026", "confirmacion": "Nueva 2026"}, "contrasena"),
        ({"confirmacion": "OtraClave99"}, "confirmacion"),
    ],
    ids=["corta", "sin-letras", "con-espacios", "no-coincide"],
)
def test_contrasena_invalida_responde_422(
    cambios: dict[str, object],
    campo: str,
    client_como: Callable[[Rol], TestClient],
    smtp_falso: Any,
) -> None:
    """HU-12 · RNF-08: la contraseña cumple la política y coincide con la confirmación."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)

    respuesta = root.post(COMPLETAR, json=_datos_completar(token, **cambios))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert campo in error["campos"]
    if campo == "contrasena":
        assert error["campos"][campo] == MENSAJE_POLITICA_CONTRASENA


def test_nombres_con_numeros_responde_422_y_el_registro_sigue_incompleto(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any, db: Session
) -> None:
    """HU-12 · RF-03: los nombres solo llevan letras y el registro no se completa."""
    root = client_como(Rol.ROOT)
    admin_id, token = _invitar(root, smtp_falso)

    respuesta = root.post(COMPLETAR, json=_datos_completar(token, nombres="1234"))

    assert respuesta.status_code == 422
    assert "nombres" in respuesta.json()["error"]["campos"]
    administrador = db.get(Usuario, admin_id)
    assert administrador is not None
    assert administrador.registro_completo is False


# ---------- Reenvío de la invitación ----------


def test_reenviar_invalida_el_enlace_anterior_y_crea_uno_nuevo(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any, db: Session
) -> None:
    """HU-10: reenviar invalida el enlace anterior y deja una nueva invitación de 72 horas."""
    root = client_como(Rol.ROOT)
    admin_id, token_viejo = _invitar(root, smtp_falso)

    respuesta = root.post(f"{RUTA}/{admin_id}/invitacion")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "invitacion_pendiente"
    assert respuesta.json()["invitacion_expira_en"]
    assert len(smtp_falso.enviados) == 2
    token_nuevo = _token_de_correo(smtp_falso.enviados[-1])
    assert token_nuevo != token_viejo

    assert root.post(VALIDAR, json={"token": token_viejo}).status_code == 400
    assert root.post(VALIDAR, json={"token": token_nuevo}).status_code == 200
    assert (
        db.scalar(
            select(RegistroAuditoria.accion).where(
                RegistroAuditoria.accion == "administrador.reenviar_invitacion"
            )
        )
        == "administrador.reenviar_invitacion"
    )


def test_reenviar_permite_completar_una_cuenta_antigua_sin_correo(
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
    db: Session,
) -> None:
    """HU-10: las cuentas incompletas anteriores reciben el correo al reenviar."""
    root = client_como(Rol.ROOT)
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario="antiguo", registro_completo=False)
    assert administrador.email is None

    sin_correo = root.post(f"{RUTA}/{administrador.id}/invitacion")
    respuesta = root.post(
        f"{RUTA}/{administrador.id}/invitacion",
        json={"email": "antiguo@avianco.test"},
    )

    assert sin_correo.status_code == 422
    assert "email" in sin_correo.json()["error"]["campos"]
    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "antiguo@avianco.test"
    assert str(smtp_falso.enviados[-1]["To"]) == "antiguo@avianco.test"


@pytest.mark.parametrize("motivo", ["completo", "inactivo"])
def test_reenviar_a_un_registro_completo_o_inactivo_responde_409(
    motivo: str,
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
) -> None:
    """HU-10: solo se reenvía a un administrador activo con el registro incompleto."""
    root = client_como(Rol.ROOT)
    administrador = crear_usuario(
        Rol.ADMIN,
        nombre_usuario="jtorres",
        email="jorge.torres@avianco.test",
        registro_completo=motivo == "completo",
        activo=motivo != "inactivo",
    )

    respuesta = root.post(f"{RUTA}/{administrador.id}/invitacion")

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["codigo"] == "estado_invalido"


# ---------- Desactivar y reactivar con una invitación ----------


def test_desactivar_invalida_la_invitacion_y_reactivar_exige_reenviarla(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-11 · HU-12: un administrador inactivo no puede usar el enlace pendiente."""
    root = client_como(Rol.ROOT)
    admin_id, token = _invitar(root, smtp_falso)

    desactivar = root.post(f"{RUTA}/{admin_id}/desactivar")
    validar = root.post(VALIDAR, json={"token": token})
    reactivar = root.post(f"{RUTA}/{admin_id}/reactivar")

    assert desactivar.status_code == 200
    assert desactivar.json()["estado"] == "inactivo"
    assert validar.status_code == 400
    assert reactivar.status_code == 200
    assert reactivar.json()["estado"] == "invitacion_vencida"

    reenvio = root.post(f"{RUTA}/{admin_id}/invitacion")
    assert reenvio.status_code == 200
    assert reenvio.json()["estado"] == "invitacion_pendiente"


# ---------- Restablecimiento de contraseña ----------


def test_un_administrador_invitado_no_puede_usar_olvide_mi_contrasena(
    client: TestClient, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-12: sin contraseña, el restablecimiento no permite saltarse la invitación."""
    root = client_como(Rol.ROOT)
    _invitar(root, smtp_falso)
    smtp_falso.enviados.clear()

    respuesta = client.post(
        "/api/v1/auth/restablecimiento", json={"email": "jorge.torres@avianco.test"}
    )

    assert respuesta.status_code == 202
    assert not smtp_falso.enviados


def test_al_completar_el_registro_ya_puede_restablecer_su_contrasena(
    client: TestClient, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-12: con el registro completo, el flujo de HU-05 vuelve a estar disponible."""
    root = client_como(Rol.ROOT)
    _, token = _invitar(root, smtp_falso)
    assert root.post(COMPLETAR, json=_datos_completar(token)).status_code == 200
    smtp_falso.enviados.clear()

    respuesta = client.post(
        "/api/v1/auth/restablecimiento", json={"email": "jorge.torres@avianco.test"}
    )

    assert respuesta.status_code == 202
    assert len(smtp_falso.enviados) == 1
    assert "contraseña" in str(smtp_falso.enviados[0]["Subject"]).lower()
