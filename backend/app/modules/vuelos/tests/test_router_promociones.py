"""Contrato HTTP de las promociones (HU-17, docs/api/iteracion-1.md)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.noticias import service as noticias_service
from app.modules.vuelos.models import Promocion
from app.modules.vuelos.tests.fabricas import (
    crear_promocion_bd,
    crear_vuelo,
    cuerpo_promocion,
    iniciar_sesion_admin,
)

SALIDA = datetime(2099, 3, 1, 10, 0, tzinfo=UTC)


def _iso(momento: datetime) -> str:
    return momento.isoformat()


def test_crear_promocion_responde_201_con_el_contrato(
    client: TestClient, db: Session, crear_usuario
) -> None:
    """HU-17: el POST devuelve la promoción con su vuelo, clases y estado."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)
    ahora = datetime.now(UTC)
    cuerpo = cuerpo_promocion(
        porcentaje=15,
        clases=["economica", "primera"],
        inicio=_iso(ahora - timedelta(hours=1)),
        fin=_iso(ahora + timedelta(days=7)),
    )

    respuesta = client.post(f"/api/v1/vuelos/{vuelo.id}/promociones", json=cuerpo)

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["porcentaje"] == 15
    assert datos["clases"] == ["economica", "primera"]
    assert datos["estado"] == "vigente"
    assert datos["vuelo_id"] == vuelo.id
    assert datos["vuelo_codigo"] == vuelo.codigo
    assert datos["origen"]["codigo"] == vuelo.origen_codigo
    assert datos["destino"]["codigo"] == vuelo.destino_codigo
    assert datos["creada_en"] is not None


def test_crear_promocion_inexistente_responde_404(client: TestClient, crear_usuario) -> None:
    """HU-17: un vuelo inexistente responde 404 no_encontrado."""
    iniciar_sesion_admin(client, crear_usuario)

    respuesta = client.post("/api/v1/vuelos/999999/promociones", json=cuerpo_promocion())

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "no_encontrado"


def test_crear_promocion_duplicada_responde_409_con_la_clase(
    client: TestClient, db: Session, crear_usuario
) -> None:
    """HU-17 · RF-23: una segunda promoción para la misma clase responde 409 con `campos`."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)
    cuerpo = cuerpo_promocion()
    assert client.post(f"/api/v1/vuelos/{vuelo.id}/promociones", json=cuerpo).status_code == 201

    respuesta = client.post(f"/api/v1/vuelos/{vuelo.id}/promociones", json=cuerpo)

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "promocion_duplicada"
    assert "clases" in error["campos"]


def test_crear_promocion_en_vuelo_cerrado_responde_409(
    client: TestClient, db: Session, crear_usuario
) -> None:
    """HU-17 · RF-23: un vuelo cancelado o que ya salió responde 409 vuelo_cerrado."""
    iniciar_sesion_admin(client, crear_usuario)
    cancelado = crear_vuelo(db, salida=SALIDA, estado="cancelado")

    respuesta = client.post(f"/api/v1/vuelos/{cancelado.id}/promociones", json=cuerpo_promocion())

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["codigo"] == "vuelo_cerrado"


def test_crear_promocion_con_fechas_invalidas_responde_422(
    client: TestClient, db: Session, crear_usuario
) -> None:
    """HU-17 · RF-23: el fin debe ser posterior al inicio."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)
    ahora = datetime.now(UTC)
    cuerpo = cuerpo_promocion(
        inicio=_iso(ahora + timedelta(days=2)),
        fin=_iso(ahora + timedelta(days=1)),
    )

    respuesta = client.post(f"/api/v1/vuelos/{vuelo.id}/promociones", json=cuerpo)

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "fin" in error["campos"]


def test_crear_promocion_con_porcentaje_invalido_responde_422(
    client: TestClient, db: Session, crear_usuario
) -> None:
    """HU-17 · SUP-38: el porcentaje debe estar entre 1 y 90."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)

    respuesta = client.post(
        f"/api/v1/vuelos/{vuelo.id}/promociones",
        json=cuerpo_promocion(porcentaje=0),
    )

    assert respuesta.status_code == 422
    assert "porcentaje" in respuesta.json()["error"]["campos"]


def test_crear_promocion_hace_rollback_si_falla_la_noticia(
    client: TestClient,
    db: Session,
    crear_usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-17 · RNF-17: si falla la noticia no queda ni la promoción ni la auditoría."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)

    def _falla(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("fallo simulado al publicar la noticia")

    monkeypatch.setattr(noticias_service, "publicar_noticia_promocion", _falla)

    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/vuelos/{vuelo.id}/promociones", json=cuerpo_promocion())

    assert db.scalar(select(func.count()).select_from(Promocion)) == 0


def test_listar_promociones_filtra_por_estado_y_pagina(
    client: TestClient, db: Session, crear_usuario
) -> None:
    """HU-17: el listado filtra por el estado efectivo y respeta la paginación."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)
    ahora = datetime.now(UTC)
    crear_promocion_bd(
        db,
        vuelo,
        clases=["economica"],
        inicio=ahora - timedelta(hours=1),
        fin=ahora + timedelta(days=1),
    )
    crear_promocion_bd(
        db,
        vuelo,
        clases=["primera"],
        inicio=ahora - timedelta(hours=1),
        fin=ahora + timedelta(days=1),
    )

    todas = client.get("/api/v1/promociones", params={"por_pagina": 1})
    vigentes = client.get("/api/v1/promociones", params={"estado": "vigente"})
    programadas = client.get("/api/v1/promociones", params={"estado": "programada"})

    assert todas.status_code == 200
    assert todas.json()["total"] == 2
    assert todas.json()["pagina"] == 1
    assert todas.json()["por_pagina"] == 1
    assert len(todas.json()["items"]) == 1
    assert vigentes.json()["total"] == 2
    assert programadas.json()["total"] == 0
