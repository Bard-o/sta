import pytest

from app.core.security import (
    Rol,
    crear_token,
    cumple_politica_contrasena,
    hash_contrasena,
    leer_token,
    verificar_contrasena,
)


def test_el_hash_es_argon2id_con_sal_y_no_contiene_la_contrasena():
    # RNF-08: hash adaptativo y con sal, nunca en texto plano.
    primero = hash_contrasena("Clave1234")
    segundo = hash_contrasena("Clave1234")
    assert primero.startswith("$argon2id$")
    assert "Clave1234" not in primero
    assert primero != segundo


def test_verificar_contrasena():
    guardado = hash_contrasena("Clave1234")
    assert verificar_contrasena("Clave1234", guardado)
    assert not verificar_contrasena("Clave12345", guardado)
    assert not verificar_contrasena("Clave1234", None)
    assert not verificar_contrasena("Clave1234", "no-es-un-hash")


@pytest.mark.parametrize(
    ("contrasena", "cumple"),
    [
        ("Clave123", True),
        ("ñandú2026", True),
        ("corta1", False),
        ("sinnumeros", False),
        ("12345678", False),
    ],
)
def test_politica_de_contrasena(contrasena: str, cumple: bool):
    # RNF-08: mínimo 8 caracteres, al menos una letra y un número.
    assert cumple_politica_contrasena(contrasena) is cumple


def test_el_token_conserva_usuario_rol_y_version():
    datos = leer_token(crear_token(7, Rol.ADMIN, 3))
    assert datos is not None
    assert (datos.usuario_id, datos.rol, datos.version_sesion) == (7, Rol.ADMIN, 3)


def test_un_token_alterado_no_es_valido():
    token = crear_token(7, Rol.CLIENTE, 0)
    assert leer_token(token[:-2] + "xx") is None
