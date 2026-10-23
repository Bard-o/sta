"""HU-10, RF-01, RF-02 y RF-26: el root crea y lista administradores.

Cada test cita el criterio de aceptación que cubre.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Rol, verificar_contrasena
from app.modules.auditoria import service as auditoria_service
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.usuarios.models import Usuario

RUTA = "/api/v1/administradores"


def _datos(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "nombre_usuario": "jtorres",
        "contrasena_temporal": "Temporal123",
    }
    datos.update(cambios)
    return datos


def _administradores(db: Session) -> int:
    return db.scalar(select(func.count(Usuario.id)).where(Usuario.rol == Rol.ADMIN)) or 0


def _auditorias(db: Session) -> int:
    return db.scalar(select(func.count(RegistroAuditoria.id))) or 0


# ---------- Criterio: crear con usuario único y contraseña válida ----------


def test_crear_administrador_responde_201_y_lo_guarda_con_registro_incompleto(
    db: Session, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10: el root crea el administrador y queda en registro incompleto hasta HU-12."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre_usuario"] == "jtorres"
    assert cuerpo["nombres"] is None
    assert cuerpo["apellidos"] is None
    assert cuerpo["estado"] == "registro_incompleto"
    assert cuerpo["creado_en"]
    administrador = db.get(Usuario, cuerpo["id"])
    assert administrador is not None
    assert administrador.rol == Rol.ADMIN
    assert administrador.activo is True
    assert administrador.registro_completo is False
    assert administrador.email is None
    # RNF-08: la contraseña no viaja de vuelta ni se guarda en claro.
    assert "contrasena" not in json.dumps(cuerpo)


def test_la_contrasena_temporal_se_guarda_con_hash(
    db: Session, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10 · RNF-08: la contraseña temporal se guarda con Argon2id, nunca en claro."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos())

    administrador = db.get(Usuario, respuesta.json()["id"])
    assert administrador is not None
    assert administrador.password_hash.startswith("$argon2")
    assert "Temporal123" not in administrador.password_hash
    assert verificar_contrasena("Temporal123", administrador.password_hash)


@pytest.mark.parametrize(
    "contrasena", ["corta1", "sinnumeros", "12345678"], ids=["corta", "sin-numeros", "sin-letras"]
)
def test_contrasena_temporal_que_no_cumple_la_politica_responde_422(
    contrasena: str, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10 · RNF-08: una contraseña fuera de la política es rechazada campo por campo."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos(contrasena_temporal=contrasena))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "contrasena_temporal" in error["campos"]


@pytest.mark.parametrize(
    "nombre", ["ab", "con espacio", "usu@rio"], ids=["corto", "espacio", "arroba"]
)
def test_nombre_usuario_con_formato_invalido_responde_422(
    nombre: str, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10: el nombre de usuario debe tener 3 a 50 caracteres válidos."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos(nombre_usuario=nombre))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "nombre_usuario" in error["campos"]


# ---------- Criterio: un nombre de usuario existente es rechazado ----------


@pytest.mark.parametrize(
    "rol_existente", [Rol.ADMIN, Rol.CLIENTE, Rol.ROOT], ids=["admin", "cliente", "root"]
)
def test_nombre_usuario_que_ya_existe_responde_409(
    rol_existente: Rol,
    db: Session,
    client_como: Callable[[Rol], TestClient],
    crear_usuario: Callable[..., Any],
) -> None:
    """HU-10 · RF-04 · SUP-18: el nombre de usuario es único en todo el sistema.

    `client_como(Rol.ROOT)` crea antes el root `root_test`; los otros roles se crean aquí con
    el mismo nombre para comprobar que la unicidad cruza roles.
    """
    root = client_como(Rol.ROOT)
    nombre = "root_test" if rol_existente is Rol.ROOT else "jtorres"
    if rol_existente is not Rol.ROOT:
        crear_usuario(rol_existente, nombre_usuario=nombre)

    respuesta = root.post(RUTA, json=_datos(nombre_usuario=nombre))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "nombre_usuario" in error["campos"]


def test_nombre_usuario_repetido_con_otras_mayusculas_responde_409(
    client_como: Callable[[Rol], TestClient], crear_usuario: Callable[..., Any]
) -> None:
    """HU-10 · SUP-18: la unicidad del nombre de usuario no distingue mayúsculas."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.ADMIN, nombre_usuario="JTorres")

    respuesta = root.post(RUTA, json=_datos(nombre_usuario="jtorres"))

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["codigo"] == "datos_duplicados"


def test_un_rechazo_por_duplicado_no_crea_administrador_ni_auditoria(
    db: Session, client_como: Callable[[Rol], TestClient], crear_usuario: Callable[..., Any]
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


# ---------- Criterio: un usuario que no es root recibe un rechazo de autorización ----------


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.ADMIN], ids=["cliente", "admin"])
def test_cliente_y_admin_no_pueden_crear_administradores(
    rol: Rol, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10 · RF-02 · RNF-10: solo el root crea administradores, también por API directa."""
    sesion = client_como(rol)

    respuesta = sesion.post(RUTA, json=_datos())

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "sin_permiso"


def test_sin_sesion_crear_administrador_responde_401(client: TestClient) -> None:
    """HU-10 · RNF-10: sin sesión el endpoint responde 401 no_autenticado."""
    respuesta = client.post(RUTA, json=_datos())

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"


# ---------- Criterio: ninguna interfaz permite crear un segundo root ----------


def test_el_rol_del_cuerpo_se_ignora_y_el_administrador_nace_como_admin(
    db: Session, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10 · RF-01: el cuerpo no puede pedir otro root; el rol lo fija el servidor."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos(rol="root"))

    assert respuesta.status_code == 201
    administrador = db.get(Usuario, respuesta.json()["id"])
    assert administrador is not None
    assert administrador.rol == Rol.ADMIN
    assert db.scalar(select(func.count(Usuario.id)).where(Usuario.rol == Rol.ROOT)) == 1


def test_el_contrato_no_expone_un_campo_para_elegir_el_rol(client: TestClient) -> None:
    """HU-10 · RF-01: ningún cuerpo de la API permite crear un root."""
    esquemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert "rol" not in esquemas["AdministradorEntrada"]["properties"]


# ---------- Criterio: la creación queda en la auditoría sin la contraseña ----------


def test_la_creacion_queda_en_la_auditoria_sin_la_contrasena(
    db: Session, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10 · RF-26 · SUP-36: se audita administrador.crear con el estado y sin la clave."""
    root = client_como(Rol.ROOT)

    respuesta = root.post(RUTA, json=_datos())

    registro = db.scalars(select(RegistroAuditoria)).one()
    assert registro.accion == "administrador.crear"
    assert registro.entidad == "usuario"
    assert registro.entidad_id == respuesta.json()["id"]
    assert registro.antes is None
    assert registro.despues == {
        "nombre_usuario": "jtorres",
        "rol": "admin",
        "estado": "registro_incompleto",
    }
    assert "Temporal123" not in json.dumps(registro.despues)
    assert not any("contrasena" in clave for clave in registro.despues)


def test_si_falla_la_auditoria_no_queda_el_administrador(
    db: Session,
    client_como: Callable[[Rol], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-10 · RNF-17: si falla la auditoría no queda el administrador."""
    root = client_como(Rol.ROOT)

    def fallar(*_: object, **__: object) -> None:
        raise RuntimeError("falla al registrar la auditoría")

    monkeypatch.setattr(auditoria_service, "registrar", fallar)
    administradores_antes = _administradores(db)

    with pytest.raises(RuntimeError):
        root.post(RUTA, json=_datos())

    assert _administradores(db) == administradores_antes
    assert _auditorias(db) == 0


# ---------- Listado ----------


def test_listado_del_mas_reciente_al_mas_antiguo(client_como: Callable[[Rol], TestClient]) -> None:
    """HU-10: el listado va del más reciente al más antiguo."""
    root = client_como(Rol.ROOT)
    ids = [
        root.post(RUTA, json=_datos(nombre_usuario=nombre)).json()["id"]
        for nombre in ("jtorres", "mlopez", "cruiz")
    ]

    respuesta = root.get(RUTA)

    assert respuesta.status_code == 200
    assert [administrador["id"] for administrador in respuesta.json()] == sorted(ids, reverse=True)


def test_listado_muestra_los_tres_estados(
    client_como: Callable[[Rol], TestClient], crear_usuario: Callable[..., Any]
) -> None:
    """HU-10 · HU-11: la lista muestra activo, inactivo o registro incompleto."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.ADMIN, nombre_usuario="activo")
    crear_usuario(Rol.ADMIN, nombre_usuario="inactivo", activo=False)
    crear_usuario(Rol.ADMIN, nombre_usuario="incompleto", registro_completo=False)
    crear_usuario(
        Rol.ADMIN, nombre_usuario="inactivo_incompleto", activo=False, registro_completo=False
    )

    respuesta = root.get(RUTA)

    estados = {
        administrador["nombre_usuario"]: administrador["estado"]
        for administrador in respuesta.json()
    }
    assert estados == {
        "activo": "activo",
        "inactivo": "inactivo",
        "incompleto": "registro_incompleto",
        # Un desactivado se muestra siempre inactivo; sus banderas conservan el estado previo.
        "inactivo_incompleto": "inactivo",
    }


def test_el_listado_no_incluye_al_root_ni_a_los_clientes(
    client_como: Callable[[Rol], TestClient], crear_usuario: Callable[..., Any]
) -> None:
    """HU-10: el listado es de administradores, no de todas las cuentas."""
    root = client_como(Rol.ROOT)
    crear_usuario(Rol.CLIENTE, nombre_usuario="lauragomez")
    crear_usuario(Rol.ADMIN, nombre_usuario="jtorres")

    respuesta = root.get(RUTA)

    assert [administrador["nombre_usuario"] for administrador in respuesta.json()] == ["jtorres"]


def test_el_administrador_creado_inicia_sesion_con_la_contrasena_temporal(
    client: TestClient, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-10: la contraseña temporal sirve para el primer ingreso, con el registro incompleto."""
    root = client_como(Rol.ROOT)
    assert root.post(RUTA, json=_datos()).status_code == 201
    client.cookies.clear()

    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": "jtorres", "contrasena": "Temporal123"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "admin"
    assert respuesta.json()["registro_completo"] is False
