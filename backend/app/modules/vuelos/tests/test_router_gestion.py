"""Endpoints del listado de gestión y la edición de vuelos (HU-15)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.noticias import service as noticias_service
from app.modules.noticias.models import Noticia
from app.modules.reservas.service import OcupacionVuelo
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import (
    crear_vuelo,
    cuerpo_vuelo,
    iniciar_sesion_admin,
    simular_ocupacion,
)

RUTA_VUELOS = "/api/v1/vuelos"


def ruta_gestion(vuelo_id: int) -> str:
    return f"{RUTA_VUELOS}/{vuelo_id}/gestion"


# ---------- GET /vuelos (HU-15) ----------


def test_listar_vuelos_devuelve_la_pagina_del_administrador(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-15: el listado del administrador trae ocupación, bloqueos y paginación."""
    iniciar_sesion_admin(client, crear_usuario)
    tarde = crear_vuelo(db, salida=datetime(2026, 12, 10, 15, 0, tzinfo=UTC))
    temprano = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))

    respuesta = client.get(RUTA_VUELOS)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert [item["id"] for item in cuerpo["items"]] == [temprano.id, tarde.id]
    assert cuerpo["total"] == 2
    assert cuerpo["pagina"] == 1
    assert cuerpo["por_pagina"] == 20
    primero = cuerpo["items"][0]
    assert primero["ocupacion"]["economica"] == {
        "capacidad": 125,
        "vendidas": 0,
        "reservadas": 0,
        "disponibles": 125,
    }
    assert primero["editable"] is True
    assert primero["cancelable"] is True
    assert primero["motivo_no_editable"] is None


def test_listar_vuelos_aplica_filtros_y_paginacion(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-15: los filtros `desde`, `hasta` y `q` y la paginación siguen el contrato."""
    iniciar_sesion_admin(client, crear_usuario)
    crear_vuelo(db, destino="BOG", salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    medellin = crear_vuelo(db, destino="MDE", salida=datetime(2026, 12, 10, 12, 0, tzinfo=UTC))
    crear_vuelo(db, destino="CLO", salida=datetime(2026, 12, 11, 11, 0, tzinfo=UTC))

    filtrado = client.get(
        RUTA_VUELOS,
        params={"desde": "2026-12-10", "hasta": "2026-12-10", "q": "medellin"},
    )
    paginado = client.get(RUTA_VUELOS, params={"pagina": 2, "por_pagina": 2})

    assert [item["id"] for item in filtrado.json()["items"]] == [medellin.id]
    assert paginado.json()["total"] == 3
    assert len(paginado.json()["items"]) == 1


@pytest.mark.parametrize("parametros", [{"pagina": 0}, {"por_pagina": 101}])
def test_listar_vuelos_rechaza_la_paginacion_invalida(
    client_como: Callable[[Rol], TestClient], parametros: dict[str, int]
) -> None:
    """HU-15 · IU-07: la paginación inválida responde 422 con el campo señalado."""
    respuesta = client_como(Rol.ADMIN).get(RUTA_VUELOS, params=parametros)

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert next(iter(parametros)) in error["campos"]


# ---------- GET /vuelos/{id}/gestion (HU-15) ----------


def test_gestion_devuelve_ocupacion_y_motivo_de_bloqueo(
    client_como: Callable[[Rol], TestClient],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-15 · RF-18: el detalle de gestión explica por qué no se puede editar."""
    admin = client_como(Rol.ADMIN)
    vuelo = crear_vuelo(db)
    simular_ocupacion(
        monkeypatch,
        {vuelo.id: OcupacionVuelo(reservadas_economica=3, reservas_activas=1)},
    )

    respuesta = admin.get(ruta_gestion(vuelo.id))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["editable"] is False
    assert cuerpo["motivo_no_editable"] == "El vuelo tiene reservas activas o compras."
    assert cuerpo["cancelable"] is True
    assert cuerpo["tiquetes_vendidos"] == 0
    assert cuerpo["reservas_activas"] == 1
    assert cuerpo["ocupacion"]["primera"]["vendidas"] == 0
    assert cuerpo["ocupacion"]["economica"]["reservadas"] == 3
    assert cuerpo["ocupacion"]["economica"]["disponibles"] == 122


def test_gestion_de_un_vuelo_inexistente_responde_404(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-15: un vuelo que no existe responde 404 con el formato único de error."""
    respuesta = client_como(Rol.ADMIN).get(ruta_gestion(999_999))

    assert respuesta.status_code == 404
    error = respuesta.json()["error"]
    assert error["codigo"] == "no_encontrado"
    assert error["mensaje"] == "El vuelo no existe."


# ---------- PUT /vuelos/{id} (HU-15) ----------


def test_editar_vuelo_devuelve_200_y_conserva_el_codigo(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-15 · RF-18: editar recalcula el vuelo, conserva el código y lo responde."""
    iniciar_sesion_admin(client, crear_usuario)
    vuelo = crear_vuelo(db, origen="PEI", destino="BOG", duracion_minutos=50)

    respuesta = client.put(
        f"{RUTA_VUELOS}/{vuelo.id}",
        json=cuerpo_vuelo(
            origen="PEI",
            destino="MAD",
            duracion_minutos=600,
            precio_economica=2_500_000,
        ),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id"] == vuelo.id
    assert cuerpo["codigo"] == vuelo.codigo
    assert cuerpo["tipo"] == "internacional"
    assert cuerpo["capacidad"] == {"primera": 50, "economica": 200, "total": 250}
    assert cuerpo["destino"]["codigo"] == "MAD"
    assert cuerpo["precio_economica"] == 2_500_000
    assert cuerpo["editable"] is True


def test_editar_vuelo_inexistente_responde_404(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-15: editar un vuelo que no existe responde 404 no_encontrado."""
    respuesta = client_como(Rol.ADMIN).put(f"{RUTA_VUELOS}/999999", json=cuerpo_vuelo())

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "no_encontrado"


def test_editar_vuelo_con_reservas_responde_409(
    client_como: Callable[[Rol], TestClient],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-15 · RF-18: con reservas activas responde 409 vuelo_con_reservas."""
    admin = client_como(Rol.ADMIN)
    vuelo = crear_vuelo(db)
    simular_ocupacion(monkeypatch, {vuelo.id: OcupacionVuelo(reservas_activas=1)})

    respuesta = admin.put(f"{RUTA_VUELOS}/{vuelo.id}", json=cuerpo_vuelo())

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "vuelo_con_reservas"
    assert error["mensaje"] == "El vuelo tiene reservas activas o compras y no se puede editar."


def test_editar_vuelo_realizado_responde_409(
    client_como: Callable[[Rol], TestClient],
    db: Session,
) -> None:
    """HU-15 · RF-18: un vuelo realizado responde 409 vuelo_cerrado."""
    admin = client_como(Rol.ADMIN)
    vuelo = crear_vuelo(db, estado="realizado")

    respuesta = admin.put(f"{RUTA_VUELOS}/{vuelo.id}", json=cuerpo_vuelo())

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["codigo"] == "vuelo_cerrado"


def test_editar_vuelo_duplicado_responde_409(
    client_como: Callable[[Rol], TestClient],
    db: Session,
) -> None:
    """HU-15 · RF-16: editar hacia la ruta y hora de otro vuelo responde 409."""
    admin = client_como(Rol.ADMIN)
    crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    otro = crear_vuelo(db, salida=datetime(2026, 12, 11, 11, 0, tzinfo=UTC))

    respuesta = admin.put(
        f"{RUTA_VUELOS}/{otro.id}",
        json=cuerpo_vuelo(
            origen="PEI", destino="BOG", fecha_salida="2026-12-10", hora_salida="06:00"
        ),
    )

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "vuelo_duplicado"
    assert "hora_salida" in error["campos"]


def test_editar_vuelo_con_datos_invalidos_responde_422(
    client_como: Callable[[Rol], TestClient],
    db: Session,
) -> None:
    """HU-15 · RF-18: las validaciones de HU-13 salen en el formato único de error."""
    admin = client_como(Rol.ADMIN)
    vuelo = crear_vuelo(db)

    respuesta = admin.put(f"{RUTA_VUELOS}/{vuelo.id}", json=cuerpo_vuelo(precio_economica=0))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "precio_economica" in error["campos"]


def test_editar_vuelo_deja_la_auditoria_del_precio(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-15 · RF-26: el cambio de precio queda en la auditoría con antes y después."""
    iniciar_sesion_admin(client, crear_usuario)
    creado = client.post(RUTA_VUELOS, json=cuerpo_vuelo())
    assert creado.status_code == 201
    vuelo_id = creado.json()["id"]

    respuesta = client.put(
        f"{RUTA_VUELOS}/{vuelo_id}", json=cuerpo_vuelo(precio_economica=2_500_000)
    )

    assert respuesta.status_code == 200
    registro = db.scalars(
        select(RegistroAuditoria).where(
            RegistroAuditoria.accion == "vuelo.editar",
            RegistroAuditoria.entidad_id == vuelo_id,
        )
    ).one()
    assert registro.antes == {"precio_economica": 2_450_000}
    assert registro.despues == {"precio_economica": 2_500_000}


def test_si_falla_la_noticia_no_queda_la_edicion_ni_la_auditoria(
    client: TestClient,
    crear_usuario: Callable[..., Any],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-15 · RNF-17: si falla la noticia, se revierte el vuelo y su auditoría."""
    iniciar_sesion_admin(client, crear_usuario)
    creado = client.post(RUTA_VUELOS, json=cuerpo_vuelo())
    assert creado.status_code == 201
    vuelo_id = creado.json()["id"]
    precio_original = creado.json()["precio_economica"]

    def fallar(*_: object, **__: object) -> None:
        raise RuntimeError("falla al actualizar la noticia")

    monkeypatch.setattr(noticias_service, "actualizar_noticias_de_vuelo", fallar)

    with pytest.raises(RuntimeError):
        client.put(f"{RUTA_VUELOS}/{vuelo_id}", json=cuerpo_vuelo(precio_economica=2_500_000))

    db.expire_all()
    assert db.get(Vuelo, vuelo_id).precio_economica == precio_original
    editados = db.scalar(
        select(func.count(RegistroAuditoria.id)).where(RegistroAuditoria.accion == "vuelo.editar")
    )
    assert editados == 0


def test_editar_vuelo_actualiza_la_noticia(
    client: TestClient, crear_usuario: Callable[..., Any], db: Session
) -> None:
    """HU-15: la noticia del vuelo queda con los datos nuevos en la misma transacción."""
    iniciar_sesion_admin(client, crear_usuario)
    creado = client.post(RUTA_VUELOS, json=cuerpo_vuelo(origen="PEI", destino="BOG"))
    vuelo_id = creado.json()["id"]

    respuesta = client.put(
        f"{RUTA_VUELOS}/{vuelo_id}",
        json=cuerpo_vuelo(origen="PEI", destino="MAD", precio_economica=2_500_000),
    )

    assert respuesta.status_code == 200
    noticia = db.scalars(select(Noticia).where(Noticia.vuelo_id == vuelo_id)).one()
    assert noticia.destino_nombre == "Madrid"
    assert noticia.precio_economica == 2_500_000
