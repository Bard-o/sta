"""Endpoints públicos de noticias (HU-19, RF-22, RF-25, RF-55)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.noticias.tests.fabricas import guardar_noticia, guardar_promocion


def _ahora() -> datetime:
    """La consulta usa la hora real; las fechas de los tests se arman a partir de ella."""
    return datetime.now(UTC)


def test_el_listado_es_publico_e_incluye_las_no_vigentes(client: TestClient, db: Session):
    """HU-19 · RF-55: sin sesión se ve el listado completo, de la más reciente a la más vieja."""
    ahora = _ahora()
    reciente = guardar_noticia(db, publicada_en=ahora - timedelta(hours=1))
    antigua = guardar_noticia(
        db, vuelo_id=77, publicada_en=ahora - timedelta(days=2), vigente=False
    )

    respuesta = client.get("/api/v1/noticias")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert [noticia["id"] for noticia in cuerpo["items"]] == [reciente.id, antigua.id]
    assert cuerpo["total"] == 2
    assert cuerpo["pagina"] == 1
    assert cuerpo["por_pagina"] == 10
    assert cuerpo["items"][0]["vigente"] is True
    assert cuerpo["items"][1]["vigente"] is False


def test_el_listado_pagina_y_usa_diez_por_pagina_por_defecto(client: TestClient, db: Session):
    """HU-19 · RF-55: `pagina` y `por_pagina` siguen el contrato (10 por defecto, máximo 50)."""
    ahora = _ahora()
    creadas = [
        guardar_noticia(db, vuelo_id=100 + indice, publicada_en=ahora - timedelta(minutes=indice))
        for indice in range(12)
    ]

    primera = client.get("/api/v1/noticias").json()
    segunda = client.get("/api/v1/noticias", params={"pagina": 2}).json()

    assert len(primera["items"]) == 10
    assert primera["total"] == 12
    assert [noticia["id"] for noticia in segunda["items"]] == [
        creadas[10].id,
        creadas[11].id,
    ]


@pytest.mark.parametrize(
    ("parametros", "campo"),
    [
        ({"pagina": 0}, "pagina"),
        ({"por_pagina": 0}, "por_pagina"),
        ({"por_pagina": 51}, "por_pagina"),
    ],
)
def test_los_parametros_de_paginacion_invalidos_responden_422(
    client: TestClient, parametros: dict[str, int], campo: str
):
    """HU-19 · IU-07: la paginación inválida trae el campo en `error.campos`."""
    respuesta = client.get("/api/v1/noticias", params=parametros)

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["error"]["codigo"] == "datos_invalidos"
    assert campo in cuerpo["error"]["campos"]


def test_el_carrusel_ordena_y_limita_a_diez(client: TestClient, db: Session):
    """HU-19 · SUP-06 · SUP-41: promociones vigentes primero, luego vuelos, máximo 10."""
    ahora = _ahora()
    promociones = [
        guardar_promocion(
            db,
            vuelo_id=200 + indice,
            promocion_id=300 + indice,
            publicada_en=ahora - timedelta(minutes=indice),
            promocion_inicio=ahora - timedelta(days=1),
            promocion_fin=ahora + timedelta(days=1),
        )
        for indice in range(8)
    ]
    vuelos = [
        guardar_noticia(
            db,
            vuelo_id=400 + indice,
            publicada_en=ahora - timedelta(hours=indice + 1),
        )
        for indice in range(4)
    ]

    respuesta = client.get("/api/v1/noticias/carrusel")

    assert respuesta.status_code == 200
    carrusel = respuesta.json()
    assert [noticia["id"] for noticia in carrusel] == [
        *[promocion.id for promocion in promociones],
        vuelos[0].id,
        vuelos[1].id,
    ]
    assert [noticia["tipo"] for noticia in carrusel[:8]] == ["promocion"] * 8


def test_el_carrusel_muestra_un_vuelo_con_promocion_una_sola_vez(client: TestClient, db: Session):
    """HU-19 · SUP-06 · SUP-41: el vuelo con promoción vigente entra solo con su promoción."""
    ahora = _ahora()
    guardar_noticia(db, vuelo_id=76, publicada_en=ahora - timedelta(hours=2))
    promocion = guardar_promocion(
        db,
        vuelo_id=76,
        publicada_en=ahora - timedelta(hours=1),
        promocion_inicio=ahora - timedelta(days=1),
        promocion_fin=ahora + timedelta(days=1),
    )

    carrusel = client.get("/api/v1/noticias/carrusel").json()

    assert [noticia["id"] for noticia in carrusel] == [promocion.id]
    assert carrusel[0]["vuelo_id"] == 76
    assert carrusel[0]["promocion"] is not None


@pytest.mark.parametrize("estado", ["agotada", "cancelada"])
def test_el_carrusel_excluye_promociones_terminadas(client: TestClient, db: Session, estado: str):
    """HU-19 · RF-25: una promoción agotada o cancelada no aparece ni como vigente."""
    ahora = _ahora()
    promo = guardar_promocion(
        db,
        vuelo_id=76,
        publicada_en=ahora - timedelta(hours=1),
        promocion_inicio=ahora - timedelta(days=1),
        promocion_fin=ahora + timedelta(days=1),
        vigente=False,
        promocion_estado=estado,
    )

    listado = client.get("/api/v1/noticias").json()["items"]
    carrusel = client.get("/api/v1/noticias/carrusel").json()

    noticia = next(item for item in listado if item["id"] == promo.id)
    assert noticia["vigente"] is False
    assert noticia["promocion"]["estado"] == estado
    assert carrusel == []


def test_la_promocion_vencida_por_fecha_se_informa_como_vencida(client: TestClient, db: Session):
    """HU-19 · RF-25: al pasar `fin`, el estado efectivo es `vencida` sin tocar la base."""
    ahora = _ahora()
    promo = guardar_promocion(
        db,
        publicada_en=ahora - timedelta(days=3),
        promocion_inicio=ahora - timedelta(days=2),
        promocion_fin=ahora - timedelta(days=1),
    )

    noticia = next(
        item for item in client.get("/api/v1/noticias").json()["items"] if item["id"] == promo.id
    )

    assert noticia["vigente"] is False
    assert noticia["promocion"]["estado"] == "vencida"
    assert promo.promocion_estado == "programada"
    assert client.get("/api/v1/noticias/carrusel").json() == []
