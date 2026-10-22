"""RNF-16: la auditoría no tiene endpoints que permitan leer, editar o borrar registros.

El issue #8 no agrega endpoints (la consulta, HU-50, llega en la iteración 4), así que no hay
matriz 401/403 que probar. En su lugar se verifica que la API no exponga ninguna ruta.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol
from app.main import app

RUTAS = [getattr(ruta, "path", "") for ruta in app.routes]


def test_no_hay_endpoints_de_auditoria():
    # RNF-16: 0 endpoints permiten consultar, editar o borrar registros de auditoría.
    assert not [ruta for ruta in RUTAS if ruta.startswith("/api/v1/auditoria")]


@pytest.mark.parametrize("metodo", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_la_api_no_permite_leer_ni_modificar_la_auditoria(
    metodo: str, client: TestClient, client_como: Callable[[Rol], TestClient]
):
    # RNF-16: incluso el root recibe 404; no hay forma de tocar los registros por HTTP.
    cliente_root = client_como(Rol.ROOT)

    respuesta = cliente_root.request(metodo, "/api/v1/auditoria/1")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "no_encontrado"
