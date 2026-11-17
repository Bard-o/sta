"""RNF-10: cada endpoint del módulo responde 401 o 403 a los roles que no lo tienen permitido.

Matriz del contrato en docs/api/iteracion-2.md. Los endpoints que todavía son stubs responden
501 (o 422 si el cuerpo vacío no pasa la validación) al rol permitido.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol

CLIENTE = (Rol.CLIENTE,)

ENDPOINTS: list[tuple[str, str, tuple[Rol, ...]]] = [
    ("GET", "/api/v1/monedero", CLIENTE),
    ("GET", "/api/v1/monedero/movimientos", CLIENTE),
    ("GET", "/api/v1/monedero/tarjetas", CLIENTE),
    ("POST", "/api/v1/monedero/tarjetas", CLIENTE),
    ("DELETE", "/api/v1/monedero/tarjetas/1", CLIENTE),
    ("POST", "/api/v1/monedero/recargas", CLIENTE),
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_matriz_de_permisos(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # Apéndice B: monedero y tarjetas son solo del cliente.
    cliente_http = client_como(rol) if rol else client
    for metodo, ruta, permitidos in ENDPOINTS:
        respuesta = cliente_http.request(metodo, ruta, json={})
        if rol in permitidos:
            assert respuesta.status_code not in (401, 403), f"{metodo} {ruta} como {rol}"
        else:
            esperado, codigo = (401, "no_autenticado") if rol is None else (403, "sin_permiso")
            assert respuesta.status_code == esperado, f"{metodo} {ruta} como {rol}"
            assert respuesta.json()["error"]["codigo"] == codigo, f"{metodo} {ruta} como {rol}"
