"""HU-01, HU-07 y HU-12: lugar de nacimiento con país, departamento y municipio.

Cada test cita el criterio de aceptación o la regla del contrato que cubre.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.usuarios.models import Usuario

REGISTRO = "/api/v1/usuarios/registro"
PERFIL = "/api/v1/usuarios/me/perfil"
LOGIN = "/api/v1/auth/login"
REGISTRO_ADMIN = "/api/v1/administradores/me/registro"
CONTRASENA = "Clave1234"
CONTRASENA_NUEVA = "MiClave2026"

SANTA_ROSA = {"pais": "CO", "municipio": "66682", "ciudad": None}


def _datos(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "tipo_documento": "CC",
        "numero_documento": "1088345921",
        "nombres": "Laura",
        "apellidos": "Gómez Ríos",
        "fecha_nacimiento": "1995-03-14",
        "lugar_nacimiento": SANTA_ROSA,
        "direccion_facturacion": "Cra. 7 # 19-28, Pereira",
        "genero": "femenino",
        "email": "laura.gomez@correo.co",
        "telefono": "310 555 0192",
        "nombre_usuario": "lauragomez",
        "contrasena": CONTRASENA,
        "acepta_politica": True,
    }
    datos.update(cambios)
    return datos


def _entrada(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "nombres": "Laura",
        "apellidos": "Gómez Ríos",
        "fecha_nacimiento": "1995-03-14",
        "lugar_nacimiento": SANTA_ROSA,
        "direccion_facturacion": "Cra. 7 # 19-28, Pereira",
        "genero": "femenino",
        "email": "laura.gomez@correo.co",
        "telefono": "310 555 0192",
    }
    datos.update(cambios)
    return datos


def _datos_admin(**cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "tipo_documento": "CC",
        "numero_documento": "10234567",
        "nombres": "Jorge",
        "apellidos": "Torres",
        "fecha_nacimiento": "1990-05-02",
        "lugar_nacimiento": {"pais": "CO", "municipio": "76001", "ciudad": None},
        "direccion_facturacion": "Cl. 5 # 38-14, Cali",
        "genero": "masculino",
        "email": "jorge.torres@avianco.test",
        "telefono": None,
        "contrasena_temporal": CONTRASENA,
        "contrasena_nueva": CONTRASENA_NUEVA,
        "confirmacion": CONTRASENA_NUEVA,
    }
    datos.update(cambios)
    return datos


def _usuario(db: Session, nombre_usuario: str = "lauragomez") -> Usuario:
    db.expire_all()
    usuario = db.scalar(select(Usuario).where(Usuario.nombre_usuario == nombre_usuario))
    assert usuario is not None
    return usuario


def _login(client: TestClient, nombre_usuario: str) -> None:
    respuesta = client.post(LOGIN, json={"usuario": nombre_usuario, "contrasena": CONTRASENA})
    assert respuesta.status_code == 200


@pytest.fixture(autouse=True)
def _sin_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ningún test abre SMTP."""
    monkeypatch.setattr("app.modules.usuarios.service.enviar_correo", lambda *_, **__: None)


def test_registro_guarda_el_lugar_estructurado_y_el_texto(client: TestClient, db: Session):
    """HU-01 (AC1): Santa Rosa de Cabal se elige por su código y el texto lo calcula el backend."""
    assert client.post(REGISTRO, json=_datos()).status_code == 201

    usuario = _usuario(db)
    assert usuario.pais_nacimiento == "CO"
    assert usuario.municipio_nacimiento == "66682"
    assert usuario.ciudad_nacimiento is None
    assert usuario.lugar_nacimiento == "Santa Rosa de Cabal, Risaralda, Colombia"


def test_registro_acepta_una_ciudad_de_otro_pais(client: TestClient, db: Session):
    """HU-01 (AC2): para otro país se elige el país y se escribe la ciudad."""
    respuesta = client.post(
        REGISTRO,
        json=_datos(lugar_nacimiento={"pais": "ES", "municipio": None, "ciudad": "  Madrid  "}),
    )

    assert respuesta.status_code == 201
    usuario = _usuario(db)
    assert usuario.pais_nacimiento == "ES"
    assert usuario.municipio_nacimiento is None
    assert usuario.ciudad_nacimiento == "Madrid"
    assert usuario.lugar_nacimiento == "Madrid, España"


def test_registro_acepta_la_ciudad_mas_larga_de_otro_pais(client: TestClient, db: Session):
    """HU-01: el texto «ciudad, país» cabe en la columna aunque la ciudad tenga 120 caracteres."""
    ciudad = "C" * 120
    respuesta = client.post(
        REGISTRO,
        json=_datos(lugar_nacimiento={"pais": "GS", "municipio": None, "ciudad": ciudad}),
    )

    assert respuesta.status_code == 201
    usuario = _usuario(db)
    assert usuario.ciudad_nacimiento == ciudad
    assert usuario.lugar_nacimiento == f"{ciudad}, Islas Georgia del Sur y Sandwich del Sur"


def test_perfil_devuelve_codigos_y_nombres(client: TestClient):
    """HU-07 (AC1): el perfil muestra «Santa Rosa de Cabal, Risaralda, Colombia»."""
    assert client.post(REGISTRO, json=_datos()).status_code == 201

    perfil = client.get(PERFIL).json()
    assert perfil["lugar_nacimiento"] == {
        "pais": "CO",
        "pais_nombre": "Colombia",
        "departamento": "66",
        "departamento_nombre": "Risaralda",
        "municipio": "66682",
        "municipio_nombre": "Santa Rosa de Cabal",
        "ciudad": None,
    }
    assert perfil["lugar_nacimiento_texto"] == "Santa Rosa de Cabal, Risaralda, Colombia"


@pytest.mark.parametrize(
    ("lugar", "campo"),
    [
        ({"pais": "ZZ", "municipio": None, "ciudad": "Madrid"}, "lugar_nacimiento.pais"),
        ({"pais": "co", "municipio": "66682", "ciudad": None}, "lugar_nacimiento.pais"),
        ({"pais": "CO", "municipio": "99999", "ciudad": None}, "lugar_nacimiento.municipio"),
        ({"pais": "CO", "municipio": None, "ciudad": None}, "lugar_nacimiento.municipio"),
        ({"pais": "CO", "municipio": "66682", "ciudad": "Pereira"}, "lugar_nacimiento.ciudad"),
        ({"pais": "ES", "municipio": "66682", "ciudad": None}, "lugar_nacimiento.municipio"),
        ({"pais": "ES", "municipio": None, "ciudad": None}, "lugar_nacimiento.ciudad"),
        ({"pais": "ES", "municipio": None, "ciudad": "   "}, "lugar_nacimiento.ciudad"),
        ({"pais": "ES", "municipio": None, "ciudad": "M" * 121}, "lugar_nacimiento.ciudad"),
    ],
    ids=[
        "pais-inexistente",
        "pais-minuscula",
        "municipio-inexistente",
        "municipio-faltante",
        "ciudad-con-colombia",
        "municipio-con-otro-pais",
        "ciudad-faltante",
        "ciudad-vacia",
        "ciudad-larga",
    ],
)
def test_registro_rechaza_combinaciones_invalidas(
    client: TestClient, lugar: dict[str, object], campo: str
):
    """HU-01: el error va en el campo exacto (`lugar_nacimiento.pais|municipio|ciudad`)."""
    respuesta = client.post(REGISTRO, json=_datos(lugar_nacimiento=lugar))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert campo in error["campos"]


def test_perfil_rechaza_un_municipio_que_no_existe(client: TestClient):
    """HU-07: el perfil aplica las mismas reglas que el registro."""
    assert client.post(REGISTRO, json=_datos()).status_code == 201

    respuesta = client.put(
        PERFIL,
        json=_entrada(lugar_nacimiento={"pais": "CO", "municipio": "99999", "ciudad": None}),
    )

    assert respuesta.status_code == 422
    assert "lugar_nacimiento.municipio" in respuesta.json()["error"]["campos"]


def test_registro_del_administrador_valida_el_lugar(client: TestClient, crear_usuario, db: Session):
    """HU-12: completar el registro del administrador usa el mismo catálogo."""
    crear_usuario(Rol.ADMIN, nombre_usuario="adminlugar", registro_completo=False)
    _login(client, "adminlugar")

    invalido = client.post(
        REGISTRO_ADMIN,
        json=_datos_admin(lugar_nacimiento={"pais": "CO", "municipio": "99999", "ciudad": None}),
    )
    assert invalido.status_code == 422
    assert "lugar_nacimiento.municipio" in invalido.json()["error"]["campos"]

    valido = client.post(
        REGISTRO_ADMIN,
        json=_datos_admin(lugar_nacimiento={"pais": "ES", "municipio": None, "ciudad": "Madrid"}),
    )
    assert valido.status_code == 200
    usuario = _usuario(db, "adminlugar")
    assert usuario.pais_nacimiento == "ES"
    assert usuario.lugar_nacimiento == "Madrid, España"


def test_cuenta_anterior_conserva_su_texto_y_debe_completar_el_perfil(
    client: TestClient, db: Session, crear_usuario
):
    """HU-07: una cuenta anterior devuelve `lugar_nacimiento: null` y su texto; al editar se
    completa el objeto estructurado."""
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="cuentaantigua")
    usuario.tipo_documento = "CC"
    usuario.numero_documento = "80123456"
    usuario.nombres = "Ana"
    usuario.apellidos = "Pérez"
    usuario.fecha_nacimiento = date(1990, 1, 1)
    usuario.lugar_nacimiento = "Pereira, Risaralda"
    usuario.direccion_facturacion = "Cra. 7 # 19-28, Pereira"
    usuario.genero = "femenino"
    usuario.email = "ana@correo.co"
    usuario.email_verificado = True
    db.commit()
    _login(client, "cuentaantigua")

    perfil = client.get(PERFIL).json()
    assert perfil["lugar_nacimiento"] is None
    assert perfil["lugar_nacimiento_texto"] == "Pereira, Risaralda"

    respuesta = client.put(
        PERFIL,
        json=_entrada(
            nombres="Ana",
            apellidos="Pérez",
            email="ana@correo.co",
            lugar_nacimiento={"pais": "CO", "municipio": "66001", "ciudad": None},
        ),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["lugar_nacimiento"]["municipio"] == "66001"
    assert respuesta.json()["lugar_nacimiento_texto"] == "Pereira, Risaralda, Colombia"
    assert _usuario(db, "cuentaantigua").municipio_nacimiento == "66001"
