"""HU-19 / RF-55: las noticias son públicas y no hay ninguna interfaz para crearlas a mano."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.security import Rol

RUTAS = ["/api/v1/noticias", "/api/v1/noticias/carrusel"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_un_visitante_puede_consultar_noticias(client: TestClient, ruta: str):
    """HU-19 / RF-55: un visitante sin sesión ve el listado y el carrusel."""
    respuesta = client.get(ruta)
    assert respuesta.status_code == 200


@pytest.mark.parametrize("ruta", RUTAS)
@pytest.mark.parametrize("rol", list(Rol))
def test_ningun_rol_recibe_401_ni_403(
    client_como: Callable[[Rol], TestClient], ruta: str, rol: Rol
):
    """HU-19 / RF-55: las noticias son públicas para todos los roles."""
    assert client_como(rol).get(ruta).status_code == 200


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
def test_no_existe_endpoint_para_publicar_noticias_a_mano(client: TestClient, metodo: str):
    """RF-55: solo lectura automática; los métodos de escritura responden 405."""
    respuesta = client.request(metodo, "/api/v1/noticias", json={})
    assert respuesta.status_code == 405
    assert respuesta.json()["error"]["codigo"] == "metodo_no_permitido"
