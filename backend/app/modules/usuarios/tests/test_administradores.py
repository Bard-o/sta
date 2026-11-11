"""HU-10, RF-01, RF-02 y RF-26: el root invita y lista administradores.

Cada test cita el criterio de aceptación que cubre.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.auditoria import service as auditoria_service
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.usuarios.models import TokenInvitacion, Usuario

RUTA = "/api/v1/administradores"


def _datos(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "nombre_usuario": "jtorres",
        "email": "jorge.torres@avianco.test",
    }
    datos.update(cambios)
    return datos


def _administradores(db: Session) -> int:
    return db.scalar(select(func.count(Usuario.id)).where(Usuario.rol == Rol.ADMIN)) or 0


def _auditorias(db: Session) -> int:
    return db.scalar(select(func.count(RegistroAuditoria.id))) or 0


def _token_de_correo(mensaje: EmailMessage) -> str:
    """Extrae el token del enlace del correo de invitación."""
    for parte in mensaje.walk():
        if parte.get_content_type() in ("text/plain", "text/html"):
            coincidencia = re.search(r"token=([A-Za-z0-9_-]+)", parte.get_content())
            if coincidencia:
                return coincidencia.group(1)
    raise AssertionError("El correo no trae el enlace de completar registro")


# ---------- Criterio: crear con usuario y correo únicos ----------


def test_crear_administrador_responde_201_y_lo_deja_invitado(
    db: Session,
    client_como: Callable[[Rol], TestClient],
    smtp_falso: Any,
) -> None:
    """HU-10: el root invita; no hay contraseña temporal ni registro completo."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre_usuario"] == "jtorres"
    assert cuerpo["email"] == "jorge.torres@avianco.test"
    assert cuerpo["nombres"] is None
    assert cuerpo["apellidos"] is None
    assert cuerpo["estado"] == "invitacion_pendiente"
    assert cuerpo["invitacion_expira_en"]
    assert cuerpo["creado_en"]
    administrador = db.get(Usuario, cuerpo["id"])
    assert administrador is not None
    assert administrador.rol == Rol.ADMIN
    assert administrador.activo is True
    assert administrador.registro_completo is False
    assert administrador.email == "jorge.torres@avianco.test"
    assert administrador.email_verificado is False
    # HU-10: nadie define la contraseña; la elige el administrador al completar.
    assert administrador.password_hash is None
    # RNF-08: la contraseña no viaja de vuelta.
    assert "contrasena" not in json.dumps(cuerpo)

    invitacion = db.scalars(
        select(TokenInvitacion).where(TokenInvitacion.usuario_id == administrador.id)
    ).one()
    assert invitacion.email == "jorge.torres@avianco.test"
    assert invitacion.usado_en is None
    assert invitacion.token_hash != _token_de_correo(smtp_falso.enviados[0])
    # SUP-17: vence en 72 horas.
    assert timedelta(hours=71, minutes=59) < invitacion.expira_en - datetime.now(UTC)


def test_el_correo_lleva_el_enlace_de_completar_registro(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-10: el enlace del correo apunta a la pantalla pública de completar el registro."""
    root = client_como(Rol.ROOT)

    assert root.post(RUTA, json=_datos()).status_code == 201

    mensaje = smtp_falso.enviados[0]
    assert str(mensaje["To"]) == "jorge.torres@avianco.test"
    assert "Completa tu registro" in str(mensaje["Subject"])
    cuerpo = mensaje.get_body().get_content()
    assert "http://localhost:5173/completar-registro?token=" in cuerpo
    assert "jtorres" in cuerpo


def test_si_falla_el_smtp_el_administrador_queda_creado_para_reenviar(
    db: Session,
    client_como: Callable[[Rol], TestClient],
    smtp_falso: Any,
) -> None:
    """HU-10: un fallo de correo no deshace la invitación; el root puede reenviarla."""
    root = client_como(Rol.ROOT)
    smtp_falso.sin_conexion = True

    respuesta = root.post(RUTA, json=_datos())

    assert respuesta.status_code == 201
    administrador = db.get(Usuario, respuesta.json()["id"])
    assert administrador is not None
    assert administrador.registro_completo is False
    assert db.scalar(select(func.count(TokenInvitacion.id))) == 1


@pytest.mark.parametrize(
    "email",
    ["sin-arroba", "sin-punto@ejemplo", "con espacio@ejemplo.com"],
    ids=["sin-arroba", "sin-punto", "con-espacio"],
)
def test_email_con_formato_invalido_responde_422(
    email: str, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-10: el correo debe tener un formato válido."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos(email=email))

    assert respuesta.status_code == 422
    assert "email" in respuesta.json()["error"]["campos"]


@pytest.mark.parametrize(
    "nombre", ["ab", "con espacio", "usu@rio"], ids=["corto", "espacio", "arroba"]
)
def test_nombre_usuario_con_formato_invalido_responde_422(
    nombre: str, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-10: el nombre de usuario debe tener 3 a 50 caracteres válidos."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos(nombre_usuario=nombre))

    assert respuesta.status_code == 422
    assert "nombre_usuario" in respuesta.json()["error"]["campos"]


# ---------- Criterio: usuario y correo existentes son rechazados ----------


@pytest.mark.parametrize(
    "rol_existente", [Rol.ADMIN, Rol.CLIENTE, Rol.ROOT], ids=["admin", "cliente", "root"]
)
def test_nombre_usuario_que_ya_existe_responde_409(
    rol_existente: Rol,
    db: Session,
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
) -> None:
    """HU-10 · RF-04 · SUP-18: el nombre de usuario es único en todo el sistema."""
    root = client_como(Rol.ROOT)
    nombre = "root_test" if rol_existente is Rol.ROOT else "jtorres"
    if rol_existente is not Rol.ROOT:
        crear_usuario(rol_existente, nombre_usuario=nombre)

    respuesta = root.post(RUTA, json=_datos(nombre_usuario=nombre))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "nombre_usuario" in error["campos"]


def test_email_que_ya_es_de_otro_administrador_responde_409(
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
) -> None:
    """HU-10 · RF-04 · SUP-18: el correo es único entre administradores."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.ADMIN, nombre_usuario="otro", email="ocupado@avianco.test")

    respuesta = root.post(RUTA, json=_datos(email="Ocupado@AVIANCO.test"))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "email" in error["campos"]


def test_el_email_de_un_cliente_no_impide_invitar_a_un_administrador(
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
) -> None:
    """SUP-18: una persona puede tener cuenta de cliente y de administrador con el mismo correo."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.CLIENTE, nombre_usuario="cliente", email="jorge.torres@avianco.test")

    respuesta = root.post(RUTA, json=_datos())

    assert respuesta.status_code == 201


def test_un_rechazo_por_duplicado_no_crea_administrador_ni_auditoria(
    db: Session,
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
) -> None:
    """HU-10 · RNF-17: un duplicado no deja rastro ni en usuarios ni en la auditoría."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")
    administradores_antes = _administradores(db)
    auditorias_antes = _auditorias(db)

    respuesta = root.post(RUTA, json=_datos())

    assert respuesta.status_code == 409
    assert _administradores(db) == administradores_antes
    assert _auditorias(db) == auditorias_antes
    assert not smtp_falso.enviados


# ---------- Criterio: autorización y rol ----------


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ADMIN], ids=["cliente", "admin"])
def test_cliente_y_admin_no_pueden_crear_administradores(
    rol: Rol, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-10 · RF-02 · RNF-10: solo el root invita, también por API directa."""
    sesion = client_como(rol)

    respuesta = sesion.post(RUTA, json=_datos())

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "sin_permiso"


def test_sin_sesion_crear_administrador_responde_401(client: TestClient) -> None:
    """HU-10 · RNF-10: sin sesión el endpoint responde 401 no_autenticado."""
    respuesta = client.post(RUTA, json=_datos())

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


def test_el_rol_del_cuerpo_se_ignora_y_el_administrador_nace_como_admin(
    db: Session, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-10 · RF-01: el cuerpo no puede pedir otro root; el rol lo fija el servidor."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos(rol="root"))

    assert respuesta.status_code == 201
    administrador = db.get(Usuario, respuesta.json()["id"])
    assert administrador is not None
    assert administrador.rol == Rol.ADMIN
    assert db.scalar(select(func.count(Usuario.id)).where(Usuario.rol == Rol.ROOT)) == 1


def test_el_contrato_no_expone_un_campo_para_elegir_el_rol_ni_contrasena(
    client: TestClient,
) -> None:
    """HU-10 · RF-01 · RNF-08: el alta no acepta rol ni contraseña."""
    esquemas = client.get("/openapi.json").json()["components"]["schemas"]

    propiedades = esquemas["AdministradorEntrada"]["properties"]
    assert "rol" not in propiedades
    assert "contrasena_temporal" not in propiedades
    assert set(propiedades) == {"nombre_usuario", "email"}


# ---------- Criterio: la creación queda en la auditoría ----------


def test_la_creacion_queda_en_la_auditoria_sin_contrasena_ni_token(
    db: Session, client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-10 · RF-26 · SUP-36: se audita administrador.crear con el estado y sin secretos."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos())

    registro = db.scalars(select(RegistroAuditoria)).one()
    assert registro.accion == "administrador.crear"
    assert registro.entidad == "usuario"
    assert registro.entidad_id == respuesta.json()["id"]
    assert registro.antes is None
    assert registro.despues == {
        "nombre_usuario": "jtorres",
        "email": "jorge.torres@avianco.test",
        "rol": "admin",
        "estado": "invitacion_pendiente",
    }
    serializado = json.dumps(registro.despues)
    assert "contrasena" not in serializado
    assert "token" not in serializado


def test_si_falla_la_auditoria_no_queda_el_administrador(
    db: Session,
    client_como: Callable[[Rol], TestClient],
    monkeypatch: pytest.MonkeyPatch,
    smtp_falso: Any,
) -> None:
    """HU-10 · RNF-17: si falla la auditoría no queda el administrador ni sale el correo."""
    root = client_como(Rol.ROOT)

    def fallar(*_: object, **__: object) -> None:
        raise RuntimeError("falla al registrar la auditoría")

    monkeypatch.setattr(auditoria_service, "registrar", fallar)
    administradores_antes = _administradores(db)

    with pytest.raises(RuntimeError):
        root.post(RUTA, json=_datos())

    assert _administradores(db) == administradores_antes
    assert _auditorias(db) == 0
    assert not smtp_falso.enviados


# ---------- Listado y estados ----------


def test_listado_del_mas_reciente_al_mas_antiguo(
    client_como: Callable[[Rol], TestClient], smtp_falso: Any
) -> None:
    """HU-10: el listado va del más reciente al más antiguo."""
    root = client_como(Rol.ROOT)
    ids = [
        root.post(RUTA, json=_datos(nombre_usuario=nombre, email=f"{nombre}@avianco.test")).json()[
            "id"
        ]
        for nombre in ("jtorres", "mlopez", "cruiz")
    ]

    respuesta = root.get(RUTA)

    assert respuesta.status_code == 200
    assert [administrador["id"] for administrador in respuesta.json()] == sorted(ids, reverse=True)


def test_listado_muestra_pendiente_vencida_activo_e_inactivo(
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
) -> None:
    """HU-10 · HU-11 · HU-12: la lista muestra los cuatro estados del contrato."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.ADMIN, nombre_usuario="activo")
    crear_usuario(Rol.ADMIN, nombre_usuario="inactivo", activo=False, registro_completo=False)
    crear_usuario(Rol.ADMIN, nombre_usuario="vencida", registro_completo=False)
    assert root.post(RUTA, json=_datos()).status_code == 201

    respuesta = root.get(RUTA)

    estados = {
        administrador["nombre_usuario"]: administrador["estado"]
        for administrador in respuesta.json()
    }
    assert estados == {
        "jtorres": "invitacion_pendiente",
        "vencida": "invitacion_vencida",
        "activo": "activo",
        # La inactividad manda sobre el estado de la invitación.
        "inactivo": "inactivo",
    }


def test_el_administrador_invitado_no_puede_iniciar_sesion(
    client: TestClient,
    client_como: Callable[[Rol], TestClient],
    smtp_falso: Any,
) -> None:
    """HU-10 · HU-12: sin contraseña no se puede entrar hasta completar la invitación."""
    root = client_como(Rol.ROOT)
    assert root.post(RUTA, json=_datos()).status_code == 201
    client.cookies.clear()

    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": "jtorres", "contrasena": "Cualquiera123"},
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "credenciales_invalidas"


def test_el_listado_no_incluye_al_root_ni_a_los_clientes(
    client_como: Callable[[Rol], TestClient], crear_usuario: Callable[..., Any], smtp_falso: Any
) -> None:
    """HU-10: el listado es de administradores, no de todas las cuentas."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez")
    crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")

    respuesta = root.get(RUTA)

    assert [administrador["nombre_usuario"] for administrador in respuesta.json()] == ["jtorres"]
