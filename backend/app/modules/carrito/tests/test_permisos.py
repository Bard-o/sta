"""RNF-10: cada endpoint del módulo responde 401 o 403 a los roles que no lo tienen permitido.

Matriz del contrato en docs/api/iteracion-2.md. Al rol permitido se le prueba con cuerpos
vacíos o ids inexistentes: lo que importa aquí es que no responda 401 ni 403.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol

CLIENTE = (Rol.CLIENTE,)

ENDPOINTS: list[tuple[str, str, tuple[Rol, ...]]] = [
    ("GET", "/api/v1/carrito", CLIENTE),
    ("POST", "/api/v1/carrito/selecciones", CLIENTE),
    ("PATCH", "/api/v1/carrito/selecciones/1", CLIENTE),
    ("DELETE", "/api/v1/carrito/selecciones/1", CLIENTE),
    ("DELETE", "/api/v1/carrito", CLIENTE),
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_matriz_de_permisos(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # Apéndice B, RF-11: el carrito es solo del cliente.
    cliente_http = client_como(rol) if rol else client
    for metodo, ruta, permitidos in ENDPOINTS:
        respuesta = cliente_http.request(metodo, ruta, json={})
        if rol in permitidos:
            assert respuesta.status_code not in (401, 403), f"{metodo} {ruta} como {rol}"
        else:
            esperado, codigo = (401, "no_autenticado") if rol is None else (403, "sin_permiso")
            assert respuesta.status_code == esperado, f"{metodo} {ruta} como {rol}"
            assert respuesta.json()["error"]["codigo"] == codigo, f"{metodo} {ruta} como {rol}"
