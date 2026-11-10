"""HU-01, HU-07 y HU-12: catálogo de países y DIVIPOLA.

Comprueba el catálogo cargado y los tres endpoints públicos, incluida su caché.
"""

import unicodedata

from fastapi.testclient import TestClient

from app.modules.usuarios import catalogos

PAISES = "/api/v1/lugares/paises"
DEPARTAMENTOS = "/api/v1/lugares/departamentos"
MUNICIPIOS = "/api/v1/lugares/departamentos/{codigo}/municipios"
CACHE = "public, max-age=86400"


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFD", texto).lower()


def test_catalogo_de_paises_es_la_lista_iso_3166():
    """HU-01: 249 países ISO 3166-1, con Colombia y España en español."""
    assert len(catalogos.PAISES) == 249
    assert catalogos.buscar_pais("CO") is not None
    assert catalogos.buscar_pais("CO").nombre == "Colombia"
    assert catalogos.buscar_pais("ES").nombre == "España"
    assert catalogos.buscar_pais("ZZ") is None


def test_catalogo_de_departamentos_tiene_los_33_de_la_divipola():
    """HU-01: 32 departamentos más Bogotá D. C."""
    assert len(catalogos.DEPARTAMENTOS) == 33
    assert catalogos.buscar_departamento("11").nombre == "Bogotá D. C."
    assert catalogos.buscar_departamento("66").nombre == "Risaralda"


def test_un_municipio_pertenece_a_su_departamento():
    """HU-01: el código del municipio identifica su departamento."""
    santa_rosa = catalogos.buscar_municipio("66682")
    assert santa_rosa is not None
    assert santa_rosa.nombre == "Santa Rosa de Cabal"
    assert santa_rosa.departamento == "66"
    assert catalogos.buscar_municipio("76001").departamento == "76"


def test_catalogo_incluye_todas_las_subdivisiones_oficiales():
    """HU-01: municipios, áreas no municipalizadas e islas son lugares válidos."""
    assert len(catalogos.MUNICIPIOS) == 1122


def test_texto_del_lugar_de_nacimiento():
    """HU-01: el backend arma el texto para mostrar."""
    colombia = catalogos.resolver_lugar_nacimiento("CO", "66682", None)
    assert colombia.texto == "Santa Rosa de Cabal, Risaralda, Colombia"

    espana = catalogos.resolver_lugar_nacimiento("ES", None, "Madrid")
    assert espana.texto == "Madrid, España"


def test_paises_responde_el_catalogo_con_cache_de_un_dia(client: TestClient):
    """HU-01: el catálogo es público y se puede cachear."""
    respuesta = client.get(PAISES)

    assert respuesta.status_code == 200
    assert respuesta.headers["cache-control"] == CACHE
    assert {"codigo": "CO", "nombre": "Colombia"} in respuesta.json()


def test_departamentos_responde_los_33_con_cache(client: TestClient):
    respuesta = client.get(DEPARTAMENTOS)

    assert respuesta.status_code == 200
    assert respuesta.headers["cache-control"] == CACHE
    assert len(respuesta.json()) == 33


def test_municipios_filtra_por_departamento_y_ordena_por_nombre(client: TestClient):
    respuesta = client.get(MUNICIPIOS.format(codigo="66"))

    assert respuesta.status_code == 200
    assert respuesta.headers["cache-control"] == CACHE
    municipios = respuesta.json()
    assert {"codigo": "66682", "nombre": "Santa Rosa de Cabal"} in municipios
    assert all(municipio["codigo"].startswith("66") for municipio in municipios)
    nombres = [_sin_tildes(municipio["nombre"]) for municipio in municipios]
    assert nombres == sorted(nombres)


def test_municipios_de_un_departamento_inexistente_responde_404(client: TestClient):
    respuesta = client.get(MUNICIPIOS.format(codigo="00"))

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "no_encontrado"
