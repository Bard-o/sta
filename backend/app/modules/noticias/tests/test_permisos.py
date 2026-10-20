"""HU-19 / RF-55: las noticias son públicas y no hay ninguna interfaz para crearlas a mano."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("ruta", ["/api/v1/noticias", "/api/v1/noticias/carrusel"])
def test_un_visitante_puede_consultar_noticias(client: TestClient, ruta: str):
    assert client.get(ruta).status_code not in (401, 403)


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
def test_no_existe_endpoint_para_publicar_noticias_a_mano(client: TestClient, metodo: str):
    assert client.request(metodo, "/api/v1/noticias", json={}).status_code == 405
