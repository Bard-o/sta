"""RNF-10: cada endpoint del módulo responde 401 o 403 a los roles que no lo tienen permitido.

Matriz del contrato en docs/api/iteracion-1.md. Los endpoints implementados responden según su
lógica; los que todavía son stubs, 501 (o 422 si el cuerpo vacío no pasa la validación). El
registro de clientes (HU-01) es solo para visitantes: con cualquier sesión abierta responde 403.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol

PUBLICO = None
VISITANTE: tuple[Rol, ...] = ()
SESION = (Rol.CLIENTE, Rol.ADMIN, Rol.ROOT)

ENDPOINTS: list[tuple[str, str, tuple[Rol, ...] | None]] = [
    ("POST", "/api/v1/auth/login", PUBLICO),
    ("GET", "/api/v1/auth/me", SESION),
    ("POST", "/api/v1/auth/restablecimiento", PUBLICO),
    ("POST", "/api/v1/auth/restablecimiento/confirmar", PUBLICO),
    ("POST", "/api/v1/usuarios/registro", VISITANTE),
    ("POST", "/api/v1/usuarios/verificacion", PUBLICO),
    ("POST", "/api/v1/usuarios/me/verificacion/reenviar", (Rol.CLIENTE, Rol.ADMIN)),
    ("PUT", "/api/v1/usuarios/me/contrasena", SESION),
    ("GET", "/api/v1/usuarios/me/perfil", (Rol.CLIENTE, Rol.ADMIN)),
    ("PUT", "/api/v1/usuarios/me/perfil", (Rol.CLIENTE, Rol.ADMIN)),
    ("GET", "/api/v1/usuarios/me/imagen", (Rol.CLIENTE, Rol.ADMIN)),
    ("PUT", "/api/v1/usuarios/me/imagen", (Rol.CLIENTE, Rol.ADMIN)),
    ("DELETE", "/api/v1/usuarios/me/imagen", (Rol.CLIENTE, Rol.ADMIN)),
    ("PUT", "/api/v1/usuarios/me/suscripcion", (Rol.CLIENTE,)),
    ("POST", "/api/v1/usuarios/suscripcion/baja", PUBLICO),
    ("GET", "/api/v1/usuarios/me/desactivacion", (Rol.CLIENTE,)),
    ("POST", "/api/v1/usuarios/me/desactivacion", (Rol.CLIENTE,)),
    ("GET", "/api/v1/administradores", (Rol.ROOT,)),
    ("POST", "/api/v1/administradores", (Rol.ROOT,)),
    ("POST", "/api/v1/administradores/1/desactivar", (Rol.ROOT,)),
    ("POST", "/api/v1/administradores/1/reactivar", (Rol.ROOT,)),
    ("POST", "/api/v1/administradores/me/registro", (Rol.ADMIN,)),
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_matriz_de_permisos(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    cliente_http = client_como(rol) if rol else client
    for metodo, ruta, permitidos in ENDPOINTS:
        estado = cliente_http.request(metodo, ruta, json={}).status_code
        if permitidos is VISITANTE:
            permitido = rol is None
        elif rol is None:
            permitido = permitidos is PUBLICO
        else:
            permitido = permitidos is PUBLICO or rol in permitidos
        if permitido:
            assert estado not in (401, 403), f"{metodo} {ruta} como {rol}: {estado}"
        else:
            esperado = 401 if rol is None else 403
            assert estado == esperado, f"{metodo} {ruta} como {rol}: {estado}"
