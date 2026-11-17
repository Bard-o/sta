"""RNF-10, Apéndice B: la búsqueda es pública para todos los roles, también sin sesión.

Matriz del contrato en docs/api/iteracion-2.md. Mientras sean stubs responden 501 (o 422 si
falta un parámetro obligatorio): lo importante es que nunca respondan 401 ni 403.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol

RUTAS = [
    "/api/v1/busqueda/vuelos",
    "/api/v1/busqueda/vuelos?origen=PEI&precio_min=200000&precio_max=400000",
    "/api/v1/busqueda/regresos?vuelo_ida_id=1&destino=CTG&fecha=2027-04-22",
]


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_la_busqueda_es_publica(
    rol: Rol | None, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # RF-27, Apéndice B: buscar vuelos está permitido a visitantes, clientes, admin y root.
    cliente_http = client_como(rol) if rol else client
    for ruta in RUTAS:
        estado = cliente_http.get(ruta).status_code
        assert estado not in (401, 403), f"GET {ruta} como {rol}: {estado}"
