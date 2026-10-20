"""RNF-10: cada endpoint del módulo responde 401 o 403 a los roles que no lo tienen permitido.

Matriz del contrato en docs/api/iteracion-1.md. Los endpoints que todavía son stubs responden
501 (o 422 si el cuerpo vacío no pasa la validación) al rol permitido.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol

PUBLICO = None
ADMIN = (Rol.ADMIN,)

ENDPOINTS: list[tuple[str, str, tuple[Rol, ...] | None]] = [
    ("GET", "/api/v1/ciudades", PUBLICO),
    ("GET", "/api/v1/vuelos", ADMIN),
    ("POST", "/api/v1/vuelos", ADMIN),
    ("POST", "/api/v1/vuelos/vista-previa", ADMIN),
    ("POST", "/api/v1/vuelos/recurrentes", ADMIN),
    ("POST", "/api/v1/vuelos/recurrentes/vista-previa", ADMIN),
    ("GET", "/api/v1/vuelos/1", PUBLICO),
    ("GET", "/api/v1/vuelos/1/gestion", ADMIN),
    ("PUT", "/api/v1/vuelos/1", ADMIN),
    ("POST", "/api/v1/vuelos/1/cancelar", ADMIN),
    ("GET", "/api/v1/vuelos/1/pasajeros", ADMIN),
    ("POST", "/api/v1/vuelos/1/promociones", ADMIN),
    ("GET", "/api/v1/promociones", ADMIN),
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_matriz_de_permisos(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # RF-11: solo los administradores gestionan vuelos y promociones.
    cliente_http = client_como(rol) if rol else client
    for metodo, ruta, permitidos in ENDPOINTS:
        estado = cliente_http.request(metodo, ruta, json={}).status_code
        if permitidos is PUBLICO or rol in permitidos:
            assert estado not in (401, 403), f"{metodo} {ruta} como {rol}: {estado}"
        else:
            esperado = 401 if rol is None else 403
            assert estado == esperado, f"{metodo} {ruta} como {rol}: {estado}"
