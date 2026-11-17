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
    ("POST", "/api/v1/reservas", CLIENTE),
    ("POST", "/api/v1/reservas/1/pagar", CLIENTE),
    ("POST", "/api/v1/compras", CLIENTE),
    ("GET", "/api/v1/compras/1", CLIENTE),
    ("POST", "/api/v1/compras/1/confirmar", CLIENTE),
    ("DELETE", "/api/v1/compras/1", CLIENTE),
    ("GET", "/api/v1/mis-viajes?tipo=reserva", CLIENTE),
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_matriz_de_permisos(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # Apéndice B, RNF-10: reservar, comprar y ver Mis viajes es solo del cliente: ni el
    # administrador ni el root pueden crear reservas o compras.
    cliente_http = client_como(rol) if rol else client
    for metodo, ruta, permitidos in ENDPOINTS:
        respuesta = cliente_http.request(metodo, ruta, json={})
        if rol in permitidos:
            assert respuesta.status_code not in (401, 403), f"{metodo} {ruta} como {rol}"
        else:
            esperado, codigo = (401, "no_autenticado") if rol is None else (403, "sin_permiso")
            assert respuesta.status_code == esperado, f"{metodo} {ruta} como {rol}"
            assert respuesta.json()["error"]["codigo"] == codigo, f"{metodo} {ruta} como {rol}"
