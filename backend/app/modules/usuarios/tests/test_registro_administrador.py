"""HU-12, RF-02 a RF-04 y SUP-18: el administrador completa su registro.

Cada test cita el criterio de aceptación que cubre.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Rol, verificar_contrasena
from app.core.testing import CONTRASENA_TEST
from app.modules.usuarios.models import Usuario

RUTA = "/api/v1/administradores/me/registro"
LOGIN = "/api/v1/auth/login"
REGISTRO_CLIENTE = "/api/v1/usuarios/registro"
CONTRASENA_NUEVA = "MiClave2026"


def _datos(**cambios: object) -> dict[str, object]:
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
        "contrasena_temporal": CONTRASENA_TEST,
        "contrasena_nueva": CONTRASENA_NUEVA,
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


def _login(client: TestClient, nombre_usuario: str, contrasena: str = CONTRASENA_TEST) -> Any:
    return client.post(LOGIN, json={"usuario": nombre_usuario, "contrasena": contrasena})


def _admin_incompleto(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    *,
    nombre_usuario: str = "jtorres",
) -> Any:
    """Crea un administrador con el registro incompleto e inicia su sesión."""
    administrador = crear_usuario(Rol.ADMIN, nombre_usuario=nombre_usuario, registro_completo=False)
    assert _login(client, nombre_usuario).status_code == 200
    return administrador


# ---------- Criterio: mientras el registro esté incompleto solo ve el formulario ----------


def test_admin_con_registro_incompleto_recibe_403_en_el_resto_de_endpoints(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-12 CA-1 · RF-02: el resto de funciones responde 403 registro_incompleto.

    El bloqueo lo aplica core; este test comprueba que el endpoint del formulario es la
    excepción y que el resto sigue cerrado.
    """
    _admin_incompleto(client, crear_usuario)

    respuesta = client.get("/api/v1/vuelos")

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "registro_incompleto"
    # El formulario de primer ingreso sí es accesible (responde 422 por un cuerpo incompleto).
    assert client.post(RUTA, json={}).status_code != 403


# ---------- Criterio: al completarlo la temporal deja de funcionar y se habilita el menú ----------


def test_al_completar_el_registro_la_contrasena_temporal_deja_de_funcionar(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-12 CA-2: la contraseña temporal deja de servir y la nueva inicia sesión."""
    administrador = _admin_incompleto(client, crear_usuario)

    respuesta = client.post(RUTA, json=_datos())

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["registro_completo"] is True
    assert cuerpo["email_verificado"] is True

    temporal = _login(client, administrador.nombre_usuario, CONTRASENA_TEST)
    assert temporal.status_code == 401
    assert temporal.json()["error"]["codigo"] == "credenciales_invalidas"

    nueva = _login(client, administrador.nombre_usuario, CONTRASENA_NUEVA)
    assert nueva.status_code == 200


def test_al_completar_la_sesion_actual_queda_habilitada_para_el_menu(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-12 CA-2: la misma sesión sigue abierta y ya puede usar el resto de endpoints."""
    administrador = _admin_incompleto(client, crear_usuario)
    version_sesion = administrador.version_sesion

    assert client.post(RUTA, json=_datos()).status_code == 200

    db.refresh(administrador)
    assert administrador.version_sesion == version_sesion

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["registro_completo"] is True
    assert me.json()["nombres"] == "Jorge"

    # El «menú de administrador» del frontend depende de que el resto de la API ya responda.
    assert client.get("/api/v1/vuelos").status_code == 200

    perfil = client.get("/api/v1/usuarios/me/perfil")
    assert perfil.status_code == 200
    assert perfil.json()["numero_documento"] == "10234567"


# ---------- Criterio: puede registrarse luego como cliente con su mismo documento ----------


def test_administrador_puede_registrarse_como_cliente_con_el_mismo_documento(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
    smtp_falso: Any,
) -> None:
    """HU-12 CA-3 · SUP-18: documento y correo se repiten entre roles, no dentro del rol."""
    administrador = _admin_incompleto(client, crear_usuario)
    assert client.post(RUTA, json=_datos()).status_code == 200

    client.cookies.clear()  # el registro de clientes es solo para visitantes
    respuesta = client.post(REGISTRO_CLIENTE, json=_datos_cliente())

    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == "cliente"
    db.refresh(administrador)
    assert administrador.numero_documento == "10234567"
    cliente = db.scalar(
        select(Usuario).where(
            Usuario.rol == Rol.CLIENTE, Usuario.email == "jorge.torres@avianco.test"
        )
    )
    assert cliente is not None
    assert cliente.id != administrador.id


# ---------- Criterio: documento y correo únicos entre administradores ----------


def test_el_documento_es_unico_entre_administradores(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-12 CA-4 · RF-04: un documento que ya tiene otro administrador es rechazado."""
    _admin_incompleto(client, crear_usuario, nombre_usuario="jtorres")
    assert client.post(RUTA, json=_datos()).status_code == 200

    client.cookies.clear()
    _admin_incompleto(client, crear_usuario, nombre_usuario="atorres")
    respuesta = client.post(RUTA, json=_datos(email="ana.torres@avianco.test"))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "numero_documento" in error["campos"]


def test_el_correo_es_unico_entre_administradores(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-12 CA-4 · RF-04: un correo que ya tiene otro administrador es rechazado."""
    _admin_incompleto(client, crear_usuario, nombre_usuario="jtorres")
    assert client.post(RUTA, json=_datos()).status_code == 200

    client.cookies.clear()
    _admin_incompleto(client, crear_usuario, nombre_usuario="atorres")
    respuesta = client.post(RUTA, json=_datos(numero_documento="99887766"))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_duplicados"
    assert "email" in error["campos"]


def test_el_correo_pendiente_de_otro_administrador_tambien_se_rechaza(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-12 · RF-04, HU-07: no se ocupa un correo que otro administrador espera verificar."""
    otro = crear_usuario(Rol.ADMIN, nombre_usuario="otro_admin", email="ocupado@avianco.test")
    otro.email_pendiente = "pendiente@avianco.test"
    db.commit()

    _admin_incompleto(client, crear_usuario)
    respuesta = client.post(RUTA, json=_datos(email="pendiente@avianco.test"))

    assert respuesta.status_code == 409
    assert "email" in respuesta.json()["error"]["campos"]


def test_el_correo_del_administrador_queda_verificado_y_en_minusculas(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-12 CA-4: el correo del administrador no pasa por HU-02 y se guarda normalizado."""
    administrador = _admin_incompleto(client, crear_usuario)

    respuesta = client.post(RUTA, json=_datos(email="Jorge.Torres@AVIANCO.TEST"))

    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "jorge.torres@avianco.test"
    assert respuesta.json()["email_verificado"] is True
    db.refresh(administrador)
    assert administrador.email == "jorge.torres@avianco.test"
    assert administrador.email_verificado is True
    assert administrador.email_pendiente is None


# ---------- Criterio: completarlo dos veces responde 409 ----------


def test_completar_dos_veces_responde_409_registro_ya_completo(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-12 CA-5: el segundo intento no cambia nada y usa el formato único de error."""
    administrador = _admin_incompleto(client, crear_usuario)
    assert client.post(RUTA, json=_datos()).status_code == 200

    respuesta = client.post(RUTA, json=_datos(nombres="Otro", email="otro@avianco.test"))

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "error": {
            "codigo": "registro_ya_completo",
            "mensaje": "Tu registro ya está completo.",
        }
    }
    db.refresh(administrador)
    assert administrador.nombres == "Jorge"
    assert administrador.email == "jorge.torres@avianco.test"


# ---------- Casos exigidos y de borde ----------


def test_contrasena_temporal_incorrecta_responde_422_y_no_cambia_nada(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-12: la temporal incorrecta no completa ni deja datos a medias."""
    administrador = _admin_incompleto(client, crear_usuario)

    respuesta = client.post(RUTA, json=_datos(contrasena_temporal="OtraClave99"))

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "error": {
            "codigo": "contrasena_actual_incorrecta",
            "mensaje": "La contraseña temporal no es correcta.",
            "campos": {"contrasena_temporal": "La contraseña temporal no es correcta."},
        }
    }
    db.refresh(administrador)
    assert administrador.registro_completo is False
    assert administrador.nombres is None
    assert administrador.email is None
    assert verificar_contrasena(CONTRASENA_TEST, administrador.password_hash)
    assert not verificar_contrasena(CONTRASENA_NUEVA, administrador.password_hash)


def test_fecha_nacimiento_futura_responde_422(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-12 · RF-03: la fecha de nacimiento no puede ser futura."""
    _admin_incompleto(client, crear_usuario)
    manana = (date.today() + timedelta(days=1)).isoformat()

    respuesta = client.post(RUTA, json=_datos(fecha_nacimiento=manana))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "fecha_nacimiento" in error["campos"]


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"contrasena_nueva": "corta1", "confirmacion": "corta1"}, "contrasena_nueva"),
        ({"contrasena_nueva": "12345678", "confirmacion": "12345678"}, "contrasena_nueva"),
        ({"confirmacion": "OtraClave99"}, "confirmacion"),
    ],
    ids=["corta", "sin-letras", "no-coincide"],
)
def test_contrasena_nueva_invalida_responde_422(
    cambios: dict[str, object],
    campo: str,
    client: TestClient,
    crear_usuario: Callable[..., Any],
) -> None:
    """HU-12 · RNF-08: la contraseña nueva cumple la política y coincide con la confirmación."""
    _admin_incompleto(client, crear_usuario)

    respuesta = client.post(RUTA, json=_datos(**cambios))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert campo in error["campos"]


def test_el_documento_y_correo_de_un_cliente_no_bloquean_al_administrador(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    smtp_falso: Any,
) -> None:
    """HU-12 CA-3 · SUP-18: la unicidad se evalúa por rol, también al completar el registro."""
    client.cookies.clear()
    assert client.post(REGISTRO_CLIENTE, json=_datos_cliente()).status_code == 201

    client.cookies.clear()
    _admin_incompleto(client, crear_usuario)

    assert client.post(RUTA, json=_datos()).status_code == 200


def test_sin_sesion_responde_401(client: TestClient) -> None:
    """HU-12 · RNF-10: solo el administrador con sesión completa su propio registro."""
    client.cookies.clear()

    respuesta = client.post(RUTA, json=_datos())

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "no_autenticado"
