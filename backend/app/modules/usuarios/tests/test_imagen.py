"""HU-01, HU-07 y RF-03, RF-08: imagen de perfil (subir, ver y borrar).

Cada test cita el criterio de aceptación del issue #29 que cubre.
"""

import base64
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.service import MAX_BYTES_IMAGEN, MENSAJE_IMAGEN_GRANDE

PUT_IMAGEN = "/api/v1/usuarios/me/imagen"
GET_IMAGEN = "/api/v1/usuarios/me/imagen"
DELETE_IMAGEN = "/api/v1/usuarios/me/imagen"
PERFIL = "/api/v1/usuarios/me/perfil"
LOGIN = "/api/v1/auth/login"

MENSAJE_IMAGEN_INVALIDA = "La imagen debe ser JPG o PNG."

# PNG de 1x1 con transparencia: sirve para probar la firma real del formato.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z0ZkAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def _assert_error(respuesta, estado: int, codigo: str, mensaje: str, campos=None) -> None:
    assert respuesta.status_code == estado
    esperado = {"codigo": codigo, "mensaje": mensaje}
    if campos:
        esperado["campos"] = campos
    assert respuesta.json() == {"error": esperado}


@pytest.fixture
def cliente_con_perfil(db: Session, crear_usuario, client: TestClient):
    """Cliente con todos los datos personales e iniciado sesión (como en HU-07)."""
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario="lauraimagen", email="laura@correo.co")
    usuario.tipo_documento = "CC"
    usuario.numero_documento = "1088345921"
    usuario.nombres = "Laura"
    usuario.apellidos = "Gómez"
    usuario.fecha_nacimiento = date(1995, 3, 14)
    usuario.lugar_nacimiento = "Pereira, Risaralda"
    usuario.direccion_facturacion = "Cra. 7 # 19-28, Pereira"
    usuario.genero = "femenino"
    db.commit()

    respuesta = client.post(
        LOGIN, json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST}
    )
    assert respuesta.status_code == 200
    return client, usuario


def _archivo_guardado(archivos_dir: Path, usuario: Usuario) -> Path:
    return archivos_dir / "perfiles" / str(usuario.id)


def test_sube_png_y_lo_devuelve_por_get(cliente_con_perfil, archivos_dir: Path):
    """Issue #29: una subida válida devuelve el perfil y el GET sirve la imagen."""
    client, usuario = cliente_con_perfil

    respuesta = client.put(PUT_IMAGEN, files={"imagen": ("laura.png", PNG, "image/png")})

    assert respuesta.status_code == 200
    assert respuesta.json()["imagen_url"] == "/api/v1/usuarios/me/imagen?v=1"
    assert _archivo_guardado(archivos_dir, usuario).read_bytes() == PNG

    imagen = client.get(GET_IMAGEN)
    assert imagen.status_code == 200
    assert imagen.headers["content-type"] == "image/png"
    assert imagen.content == PNG


def test_sirve_un_jpeg_con_su_media_type(cliente_con_perfil):
    """Issue #29: un JPEG se sirve como image/jpeg."""
    client, _ = cliente_con_perfil

    assert (
        client.put(PUT_IMAGEN, files={"imagen": ("laura.jpg", JPEG, "image/jpeg")}).status_code
        == 200
    )

    imagen = client.get(GET_IMAGEN)
    assert imagen.status_code == 200
    assert imagen.headers["content-type"] == "image/jpeg"
    assert imagen.content == JPEG


def test_rechaza_contenido_que_no_es_jpg_ni_png(cliente_con_perfil, archivos_dir: Path):
    """Issue #29 (criterio 1): se valida el contenido, no la extensión ni el content-type."""
    client, _ = cliente_con_perfil

    respuesta = client.put(
        PUT_IMAGEN, files={"imagen": ("laura.png", b"GIF89a" + b"\x00" * 20, "image/png")}
    )

    _assert_error(
        respuesta,
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        {"imagen": MENSAJE_IMAGEN_INVALIDA},
    )
    assert not (archivos_dir / "perfiles").exists()
    assert client.get(PERFIL).json()["imagen_url"] is None


def test_acepta_png_aunque_la_extension_no_lo_diga(cliente_con_perfil):
    """Issue #29 (criterio 1): manda la firma de los bytes, no el nombre del archivo."""
    client, _ = cliente_con_perfil

    respuesta = client.put(
        PUT_IMAGEN, files={"imagen": ("foto.txt", PNG, "application/octet-stream")}
    )

    assert respuesta.status_code == 200
    assert client.get(GET_IMAGEN).headers["content-type"] == "image/png"


def test_rechaza_imagen_de_mas_de_2_mb(cliente_con_perfil, archivos_dir: Path):
    """Issue #29 (criterio 1): una imagen de más de 2 MB se rechaza en campos.imagen."""
    client, _ = cliente_con_perfil
    grande = PNG + b"\x00" * (MAX_BYTES_IMAGEN + 1 - len(PNG))

    respuesta = client.put(PUT_IMAGEN, files={"imagen": ("laura.png", grande, "image/png")})

    _assert_error(
        respuesta,
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        {"imagen": MENSAJE_IMAGEN_GRANDE},
    )
    assert not (archivos_dir / "perfiles").exists()


def test_acepta_imagen_de_exactamente_2_mb(cliente_con_perfil):
    """Issue #29 (criterio 1): el límite es 2 MB; justo en el límite se acepta."""
    client, _ = cliente_con_perfil
    limite = PNG + b"\x00" * (MAX_BYTES_IMAGEN - len(PNG))

    assert len(limite) == MAX_BYTES_IMAGEN
    assert (
        client.put(PUT_IMAGEN, files={"imagen": ("laura.png", limite, "image/png")}).status_code
        == 200
    )


def test_archivo_vacio_se_rechaza(cliente_con_perfil):
    """Issue #29 (criterio 1): un archivo vacío no es una imagen."""
    client, _ = cliente_con_perfil

    respuesta = client.put(PUT_IMAGEN, files={"imagen": ("laura.png", b"", "image/png")})

    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["campos"]["imagen"] == MENSAJE_IMAGEN_INVALIDA


def test_imagen_url_cambia_en_cada_subida(cliente_con_perfil):
    """Issue #29 (criterio 2): imagen_url cambia cada vez para vencer el caché del navegador."""
    client, _ = cliente_con_perfil

    primera = client.put(PUT_IMAGEN, files={"imagen": ("laura.png", PNG, "image/png")})
    segunda = client.put(PUT_IMAGEN, files={"imagen": ("laura.jpg", JPEG, "image/jpeg")})

    url_primera = primera.json()["imagen_url"]
    url_segunda = segunda.json()["imagen_url"]
    assert url_primera == "/api/v1/usuarios/me/imagen?v=1"
    assert url_segunda == "/api/v1/usuarios/me/imagen?v=2"
    assert url_primera != url_segunda
    assert client.get(PERFIL).json()["imagen_url"] == url_segunda
    assert client.get(GET_IMAGEN).content == JPEG


def test_get_sin_imagen_responde_404_no_encontrado(cliente_con_perfil):
    """Issue #29 (criterio 3): GET sin imagen responde 404 no_encontrado."""
    client, _ = cliente_con_perfil

    _assert_error(
        client.get(GET_IMAGEN),
        404,
        "no_encontrado",
        "El recurso no existe.",
    )


def test_reemplaza_la_imagen_anterior(cliente_con_perfil, archivos_dir: Path):
    """Issue #29: subir otra imagen reemplaza la anterior sin dejar archivos sueltos."""
    client, usuario = cliente_con_perfil
    assert client.put(PUT_IMAGEN, files={"imagen": ("a.png", PNG, "image/png")}).status_code == 200
    assert (
        client.put(PUT_IMAGEN, files={"imagen": ("b.jpg", JPEG, "image/jpeg")}).status_code == 200
    )

    assert client.get(GET_IMAGEN).content == JPEG
    assert _archivo_guardado(archivos_dir, usuario).read_bytes() == JPEG
    assert [ruta.name for ruta in (archivos_dir / "perfiles").iterdir()] == [str(usuario.id)]


def test_borra_la_imagen_y_su_url(cliente_con_perfil, archivos_dir: Path):
    """Issue #29: borrar deja el perfil sin imagen, quita el archivo y el GET da 404."""
    client, usuario = cliente_con_perfil
    assert (
        client.put(PUT_IMAGEN, files={"imagen": ("laura.png", PNG, "image/png")}).status_code == 200
    )

    respuesta = client.delete(DELETE_IMAGEN)

    assert respuesta.status_code == 204
    assert client.get(PERFIL).json()["imagen_url"] is None
    assert not _archivo_guardado(archivos_dir, usuario).exists()
    _assert_error(client.get(GET_IMAGEN), 404, "no_encontrado", "El recurso no existe.")


def test_borrar_sin_imagen_sigue_respondiendo_204(cliente_con_perfil):
    """Issue #29: el borrado es idempotente; sin imagen también responde 204."""
    client, _ = cliente_con_perfil

    assert client.delete(DELETE_IMAGEN).status_code == 204
    assert client.delete(DELETE_IMAGEN).status_code == 204


def test_put_sin_el_campo_imagen_responde_422_campos_imagen(cliente_con_perfil):
    """Issue #29: el error de un formulario sin `imagen` sale en el formato único."""
    client, _ = cliente_con_perfil

    respuesta = client.put(PUT_IMAGEN, files={})

    _assert_error(
        respuesta,
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        {"imagen": "Este campo es obligatorio."},
    )


def test_permisos_de_la_imagen(client: TestClient, client_como):
    """Issue #29: matriz de roles con 401 no_autenticado y 403 sin_permiso."""
    for metodo in ("GET", "PUT", "DELETE"):
        _assert_error(
            client.request(metodo, PUT_IMAGEN, json={}),
            401,
            "no_autenticado",
            "Inicia sesión para continuar.",
        )

    root = client_como(Rol.ROOT)
    for metodo in ("GET", "PUT", "DELETE"):
        _assert_error(
            root.request(metodo, PUT_IMAGEN, json={}),
            403,
            "sin_permiso",
            "Tu rol no tiene permiso para esta acción.",
        )


def test_administrador_con_registro_completo_tambien_tiene_imagen(
    db: Session, crear_usuario, client: TestClient
):
    """Issue #29 + HU-07: el administrador con perfil también sube su imagen."""
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="adminimagen", email="admin@correo.co")
    admin.tipo_documento = "CC"
    admin.numero_documento = "80123456"
    admin.nombres = "Carlos"
    admin.apellidos = "Ruiz"
    admin.fecha_nacimiento = date(1988, 7, 2)
    admin.lugar_nacimiento = "Bogotá, Cundinamarca"
    admin.direccion_facturacion = "Calle 100 # 15-20, Bogotá"
    admin.genero = "masculino"
    db.commit()
    assert (
        client.post(
            LOGIN, json={"usuario": admin.nombre_usuario, "contrasena": CONTRASENA_TEST}
        ).status_code
        == 200
    )

    respuesta = client.put(PUT_IMAGEN, files={"imagen": ("admin.png", PNG, "image/png")})

    assert respuesta.status_code == 200
    assert respuesta.json()["imagen_url"] == "/api/v1/usuarios/me/imagen?v=1"
    assert client.get(GET_IMAGEN).content == PNG
