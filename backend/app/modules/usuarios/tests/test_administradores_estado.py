"""HU-11, RF-02 y RF-26: el root desactiva y reactiva administradores.

Cada test cita el criterio de aceptación que cubre.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.auditoria import service as auditoria_service
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.usuarios.models import Usuario

RUTA = "/api/v1/administradores"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def _desactivar(admin_id: int) -> str:
    return f"{RUTA}/{admin_id}/desactivar"


def _reactivar(admin_id: int) -> str:
    return f"{RUTA}/{admin_id}/reactivar"


def _login(client: TestClient, nombre_usuario: str) -> Any:
    return client.post(LOGIN, json={"usuario": nombre_usuario, "contrasena": CONTRASENA_TEST})


def _root(db: Session) -> Usuario:
    root = db.scalar(select(Usuario).where(Usuario.rol == Rol.ROOT))
    assert root is not None
    return root


def _auditorias(db: Session) -> list[RegistroAuditoria]:
    return list(db.scalars(select(RegistroAuditoria).order_by(RegistroAuditoria.id)))


# ---------- Criterio: un administrador desactivado recibe «cuenta inactiva» ----------


def test_administrador_desactivado_no_puede_iniciar_sesion(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
) -> None:
    """HU-11 CA-1 · RF-02: un administrador desactivado recibe «cuenta inactiva» al entrar."""
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")
    assert _login(client, "jtorres").status_code == 200

    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")

    respuesta = client.post(_desactivar(administrador.id))

    assert respuesta.status_code == 200
    login = _login(client, "jtorres")
    assert login.status_code == 403
    assert login.json() == {"error": {"codigo": "cuenta_inactiva", "mensaje": "Cuenta inactiva."}}
    db.refresh(administrador)
    assert administrador.activo is False


# ---------- Criterio: al reactivarlo puede volver a iniciar sesión ----------


def test_administrador_reactivado_puede_iniciar_sesion(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-11 CA-2 · RF-02: tras reactivarlo, el administrador vuelve a iniciar sesión."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")
    assert client.post(_desactivar(administrador.id)).status_code == 200
    assert _login(client, "jtorres").status_code == 403

    respuesta = client.post(_reactivar(administrador.id))

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "activo"
    login = _login(client, "jtorres")
    assert login.status_code == 200
    assert login.json()["registro_completo"] is True


# ---------- Criterio: la lista muestra el estado de cada uno ----------


def test_la_lista_muestra_activo_inactivo_y_registro_incompleto(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-11 CA-3: la lista de administradores muestra activo, inactivo o registro incompleto."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    activo = crear_usuario(Rol.ADMIN, nombre_usuario="activo")
    crear_usuario(Rol.ADMIN, nombre_usuario="incompleto", registro_completo=False)
    crear_usuario(Rol.ADMIN, nombre_usuario="inactivo", activo=False)

    estados = {
        administrador["nombre_usuario"]: administrador["estado"]
        for administrador in client.get(RUTA).json()
    }
    assert estados == {
        "activo": "activo",
        "incompleto": "registro_incompleto",
        "inactivo": "inactivo",
    }

    assert client.post(_desactivar(activo.id)).status_code == 200
    estados = {
        administrador["nombre_usuario"]: administrador["estado"]
        for administrador in client.get(RUTA).json()
    }
    assert estados["activo"] == "inactivo"

    assert client.post(_reactivar(activo.id)).status_code == 200
    estados = {
        administrador["nombre_usuario"]: administrador["estado"]
        for administrador in client.get(RUTA).json()
    }
    assert estados["activo"] == "activo"


# ---------- Criterio: desactivar cierra todas sus sesiones ----------


def test_desactivar_cierra_la_sesion_abierta_del_administrador(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-11 CA-4: desactivar cierra todas las sesiones abiertas del administrador."""
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")
    version_anterior = administrador.version_sesion
    assert _login(client, "jtorres").status_code == 200
    nombre_cookie = get_settings().cookie_name
    token_anterior = client.cookies.get(nombre_cookie)
    assert token_anterior is not None

    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    assert client.post(_desactivar(administrador.id)).status_code == 200

    client.cookies.clear()
    reuso = client.get(ME, headers={"Cookie": f"{nombre_cookie}={token_anterior}"})
    assert reuso.status_code == 401
    assert reuso.json()["error"]["codigo"] == "no_autenticado"

    db.refresh(administrador)
    assert administrador.version_sesion == version_anterior + 1


# ---------- Criterio: reactivar devuelve el estado anterior ----------


@pytest.mark.parametrize(
    ("registro_completo", "estado"),
    [(True, "activo"), (False, "registro_incompleto")],
    ids=["activo", "registro-incompleto"],
)
def test_reactivar_devuelve_el_estado_anterior(
    registro_completo: bool,
    estado: str,
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
) -> None:
    """HU-11 CA-4: reactivar devuelve el estado anterior, activo o registro incompleto."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    administrador = crear_usuario(
        Rol.ADMIN, nombre_usuario="jtorres", activo=False, registro_completo=registro_completo
    )

    respuesta = client.post(_reactivar(administrador.id))

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == estado
    db.refresh(administrador)
    assert administrador.activo is True


def test_desactivar_conserva_los_datos_y_el_registro_completo(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-11: el borrado es lógico; los datos y el estado al que vuelve se conservan."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    administrador = crear_usuario(
        Rol.ADMIN, nombre_usuario="jtorres", email="jorge@example.com", registro_completo=False
    )
    db.refresh(administrador)
    datos_antes = (
        administrador.nombre_usuario,
        administrador.email,
        administrador.password_hash,
        administrador.registro_completo,
    )
    total_antes = db.scalar(select(func.count()).select_from(Usuario))

    assert client.post(_desactivar(administrador.id)).status_code == 200

    db.expire_all()
    guardado = db.get(Usuario, administrador.id)
    assert guardado is not None
    assert guardado.activo is False
    assert guardado.registro_completo is False
    assert (
        guardado.nombre_usuario,
        guardado.email,
        guardado.password_hash,
        guardado.registro_completo,
    ) == datos_antes
    assert db.scalar(select(func.count()).select_from(Usuario)) == total_antes


# ---------- Criterio: cada cambio queda en la auditoría ----------


def test_desactivar_audita_el_estado_anterior_y_el_nuevo(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-11 CA-5 · RF-26: desactivar se audita con el estado anterior y el nuevo."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    root = _root(db)
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")

    assert client.post(_desactivar(administrador.id)).status_code == 200

    registro = _auditorias(db)[-1]
    assert registro.usuario_id == root.id
    assert registro.accion == "administrador.desactivar"
    assert registro.entidad == "usuario"
    assert registro.entidad_id == administrador.id
    assert registro.antes == {
        "nombre_usuario": "jtorres",
        "rol": "admin",
        "estado": "activo",
    }
    assert registro.despues == {
        "nombre_usuario": "jtorres",
        "rol": "admin",
        "estado": "inactivo",
    }
    # RNF-08: la auditoría nunca guarda contraseñas.
    assert "contrasena" not in json.dumps(registro.despues)


def test_reactivar_audita_el_estado_anterior_y_el_nuevo(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-11 CA-5 · RF-26: reactivar se audita con el estado anterior y el nuevo."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    root = _root(db)
    administrador = crear_usuario(
        Rol.ADMIN, nombre_usuario="jtorres", activo=False, registro_completo=False
    )

    assert client.post(_reactivar(administrador.id)).status_code == 200

    registro = _auditorias(db)[-1]
    assert registro.usuario_id == root.id
    assert registro.accion == "administrador.reactivar"
    assert registro.entidad == "usuario"
    assert registro.entidad_id == administrador.id
    assert registro.antes == {
        "nombre_usuario": "jtorres",
        "rol": "admin",
        "estado": "inactivo",
    }
    assert registro.despues == {
        "nombre_usuario": "jtorres",
        "rol": "admin",
        "estado": "registro_incompleto",
    }


def test_si_falla_la_auditoria_no_cambia_el_estado(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-11 · RNF-17: el cambio y su auditoría son atómicos."""

    def fallar(*_: object, **__: object) -> None:
        raise RuntimeError("falla al registrar la auditoría")

    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")
    monkeypatch.setattr(auditoria_service, "registrar", fallar)
    auditorias_antes = len(_auditorias(db))

    with pytest.raises(RuntimeError):
        client.post(_desactivar(administrador.id))

    db.expire_all()
    guardado = db.get(Usuario, administrador.id)
    assert guardado is not None
    assert guardado.activo is True
    assert len(_auditorias(db)) == auditorias_antes


# ---------- Pruebas requeridas: no_encontrado y estado_invalido ----------


@pytest.mark.parametrize("objetivo", ["inexistente", "cliente", "root"])
def test_desactivar_un_id_que_no_es_de_un_administrador_responde_404(
    objetivo: str, client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-11 · contrato: el id debe ser de un administrador; si no, 404 no_encontrado."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    admin_id = {
        "inexistente": 999_999,
        "cliente": crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez").id,
        "root": _root(db).id,
    }[objetivo]

    respuesta = client.post(_desactivar(admin_id))

    assert respuesta.status_code == 404
    assert respuesta.json() == {
        "error": {"codigo": "no_encontrado", "mensaje": "El administrador no existe."}
    }


def test_reactivar_un_id_inexistente_responde_404(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-11 · contrato: reactivar un id que no existe responde 404 no_encontrado."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")

    respuesta = client.post(_reactivar(999_999))

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "no_encontrado"


def test_desactivar_un_administrador_inactivo_responde_409(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-11 · contrato: desactivar uno inactivo responde 409 estado_invalido."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario="jtorres", activo=False)

    respuesta = client.post(_desactivar(administrador.id))

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "error": {
            "codigo": "estado_invalido",
            "mensaje": "El administrador ya está inactivo.",
        }
    }
    db.refresh(administrador)
    assert administrador.activo is False


@pytest.mark.parametrize("registro_completo", [True, False], ids=["activo", "registro-incompleto"])
def test_reactivar_un_administrador_activo_responde_409(
    registro_completo: bool,
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
) -> None:
    """HU-11 · contrato: reactivar uno que sigue activo responde 409 estado_invalido."""
    crear_usuario(Rol.ROOT, nombre_usuario="root_test")
    _login(client, "root_test")
    administrador = crear_usuario(
        Rol.ADMIN, nombre_usuario="jtorres", registro_completo=registro_completo
    )

    respuesta = client.post(_reactivar(administrador.id))

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "error": {
            "codigo": "estado_invalido",
            "mensaje": "El administrador ya está activo.",
        }
    }
    db.refresh(administrador)
    assert administrador.activo is True
