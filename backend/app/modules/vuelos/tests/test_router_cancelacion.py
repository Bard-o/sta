"""Contrato HTTP de la cancelación de un vuelo (HU-16, docs/api/iteracion-1.md)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auditoria.models import RegistroAuditoria
from app.modules.noticias import service as noticias_service
from app.modules.noticias.models import Noticia
from app.modules.reservas import service as reservas_service
from app.modules.reservas.service import OcupacionVuelo
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import (
    crear_vuelo,
    cuerpo_vuelo,
    iniciar_sesion_admin,
    simular_ocupacion,
)

SALIDA = datetime(2099, 1, 15, 10, 0, tzinfo=UTC)


def ruta(vuelo_id: int) -> str:
    return f"/api/v1/vuelos/{vuelo_id}/cancelar"


def simular_anulacion(monkeypatch: pytest.MonkeyPatch, *, total: int = 0) -> list[int]:
    llamadas: list[int] = []

    def _anular(_db: Session, vuelo_id: int) -> int:
        llamadas.append(vuelo_id)
        return total

    monkeypatch.setattr(reservas_service, "anular_reservas_de_vuelo", _anular)
    return llamadas


def test_cancelar_vuelo_responde_200_con_el_contrato(
    client: TestClient,
    db: Session,
    crear_usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-16: el POST devuelve el vuelo cancelado y cuántas reservas se anularon."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)
    codigo = vuelo.codigo
    simular_anulacion(monkeypatch, total=2)

    respuesta = client.post(ruta(vuelo.id))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["vuelo"]["id"] == vuelo.id
    assert cuerpo["vuelo"]["estado"] == "cancelado"
    assert cuerpo["vuelo"]["codigo"] == codigo
    assert cuerpo["vuelo"]["cancelable"] is False
    assert cuerpo["vuelo"]["editable"] is False
    assert cuerpo["reservas_anuladas"] == 2


def test_cancelar_vuelo_inexistente_responde_404(client: TestClient, crear_usuario) -> None:
    """HU-16: un vuelo que no existe responde 404 no_encontrado."""
    iniciar_sesion_admin(client, crear_usuario)

    respuesta = client.post(ruta(999_999))

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "no_encontrado"


def test_cancelar_vuelo_con_tiquetes_responde_409(
    client: TestClient,
    db: Session,
    crear_usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-16 · RF-19: con tiquetes vendidos responde 409 vuelo_con_tiquetes."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_ocupacion(monkeypatch, {vuelo.id: OcupacionVuelo(vendidas_economica=1)})

    respuesta = client.post(ruta(vuelo.id))

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "vuelo_con_tiquetes"
    assert error["mensaje"] == (
        "El vuelo tiene tiquetes vendidos; requiere cancelación por fuerza mayor."
    )


def test_cancelar_vuelo_realizado_responde_409(
    client: TestClient, db: Session, crear_usuario
) -> None:
    """HU-16 · RF-19: un vuelo realizado responde 409 vuelo_cerrado."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, estado="realizado", salida=SALIDA)

    respuesta = client.post(ruta(vuelo.id))

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["codigo"] == "vuelo_cerrado"


def test_cancelar_vuelo_retira_su_noticia(client: TestClient, db: Session, crear_usuario) -> None:
    """HU-16: la noticia del vuelo deja de ser vigente en la misma transacción."""
    iniciar_sesion_admin(client, crear_usuario)
    creado = client.post("/api/v1/vuelos", json=cuerpo_vuelo())
    assert creado.status_code == 201
    vuelo_id = creado.json()["id"]

    respuesta = client.post(ruta(vuelo_id))

    assert respuesta.status_code == 200
    noticia = db.scalars(select(Noticia).where(Noticia.vuelo_id == vuelo_id)).one()
    assert noticia.vigente is False


def test_cancelar_vuelo_hace_rollback_si_falla_la_cancelacion(
    client: TestClient,
    db: Session,
    crear_usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-16 · RNF-17: si falla la noticia no queda la cancelación ni la auditoría."""
    iniciar_sesion_admin(client, crear_usuario)
    creado = client.post("/api/v1/vuelos", json=cuerpo_vuelo())
    assert creado.status_code == 201
    vuelo_id = creado.json()["id"]

    def _falla(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("fallo simulado al retirar las noticias")

    monkeypatch.setattr(noticias_service, "retirar_noticias_de_vuelo", _falla)

    with pytest.raises(RuntimeError):
        client.post(ruta(vuelo_id))

    db.expire_all()
    assert db.get(Vuelo, vuelo_id).estado == "programado"
    cancelados = db.scalar(
        select(func.count(RegistroAuditoria.id)).where(RegistroAuditoria.accion == "vuelo.cancelar")
    )
    assert cancelados == 0
