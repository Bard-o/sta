"""API de compras con el monedero (HU-25, RF-39 a RF-42, RNF-17, SUP-15)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.testing import CONTRASENA_TEST
from app.modules.monedero import service as monedero_service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas.models import Transaccion
from app.modules.reservas.tests.apoyo import (
    SALIDA,
    cliente_con_perfil,
    cliente_verificado,
    entrada,
    viajero,
)
from app.modules.vuelos.tests.fabricas import crear_vuelo


def _login(client: TestClient, usuario: object) -> None:
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200


def _cuerpo(vuelo: object) -> dict[str, object]:
    return entrada([vuelo]).model_dump(mode="json")


def test_hu25_flujo_completo_de_compra_por_la_api(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: POST crea la compra pendiente, GET la consulta, POST /confirmar la cobra y

    GET devuelve el estado activo con los tiquetes emitidos.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_compra_flujo")
    vuelo = crear_vuelo(db, salida=SALIDA, precio_economica=800_000)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    _login(client, cliente)

    creada = client.post("/api/v1/compras", json=_cuerpo(vuelo))

    assert creada.status_code == 201
    compra = creada.json()
    assert compra["tipo"] == "compra"
    assert compra["estado"] == "pendiente"
    assert compra["vence_en"] is not None
    assert compra["pagada_en"] is None
    assert compra["total"] == 800_000
    assert compra["total_pendiente"] == 800_000
    assert compra["viajeros"][0]["tiquetes"][0]["estado"] == "bloqueado"

    consultada = client.get(f"/api/v1/compras/{compra['id']}")
    assert consultada.status_code == 200
    assert consultada.json()["estado"] == "pendiente"

    confirmada = client.post(f"/api/v1/compras/{compra['id']}/confirmar")
    assert confirmada.status_code == 200
    pagada = confirmada.json()
    assert pagada["estado"] == "activa"
    assert pagada["pagada_en"] is not None
    assert pagada["vence_en"] is None
    assert pagada["total_pendiente"] == 0
    assert pagada["viajeros"][0]["tiquetes"][0]["estado"] == "comprado"
    assert monedero_service.saldo_de(db, cliente.id) == 200_000

    de_nuevo = client.get(f"/api/v1/compras/{compra['id']}")
    assert de_nuevo.status_code == 200
    assert de_nuevo.json()["estado"] == "activa"


def test_hu25_los_errores_de_la_compra_usan_el_formato_unico(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RNF-17: saldo insuficiente, bloqueo vencido, estado inválido y compra ajena

    responden el formato único con el código estable del contrato.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_compra_errores")
    otro = cliente_verificado(db, crear_usuario, nombre_usuario="api_compra_ajena")
    vuelo = crear_vuelo(db, salida=SALIDA, precio_economica=800_000)
    crear_movimiento(db, cliente.id, valor=500_000, saldo_resultante=500_000)
    _login(client, cliente)

    creada = client.post("/api/v1/compras", json=_cuerpo(vuelo))
    assert creada.status_code == 201
    compra = creada.json()

    sin_saldo = client.post(f"/api/v1/compras/{compra['id']}/confirmar")
    assert sin_saldo.status_code == 409
    error = sin_saldo.json()["error"]
    assert error["codigo"] == "saldo_insuficiente"
    assert "te faltan $ 300.000" in error["mensaje"]
    assert client.get(f"/api/v1/compras/{compra['id']}").json()["estado"] == "pendiente"

    soltada = client.delete(f"/api/v1/compras/{compra['id']}")
    assert soltada.status_code == 204
    assert client.get(f"/api/v1/compras/{compra['id']}").json()["estado"] == "cancelada"

    vencida = client.post(f"/api/v1/compras/{compra['id']}/confirmar")
    assert vencida.status_code == 409
    assert vencida.json()["error"]["codigo"] == "bloqueo_vencido"

    ajena = client.get(f"/api/v1/compras/{compra['id'] + 1_000}")
    assert ajena.status_code == 404
    assert ajena.json()["error"] == {
        "codigo": "no_encontrado",
        "mensaje": "La compra no existe.",
    }

    _login(client, otro)
    no_es_suya = client.get(f"/api/v1/compras/{compra['id']}")
    assert no_es_suya.status_code == 404
    assert no_es_suya.json()["error"]["codigo"] == "no_encontrado"


def test_hu25_el_get_adelanta_el_vencimiento_del_bloqueo(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · SUP-15: si el bloqueo ya pasó, GET informa la compra vencida y confirmar

    responde `bloqueo_vencido`, aunque el planificador todavía no haya corrido.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_compra_vence")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _login(client, cliente)
    creada = client.post("/api/v1/compras", json=_cuerpo(vuelo))
    assert creada.status_code == 201
    compra_id = creada.json()["id"]

    compra = db.get(Transaccion, compra_id)
    assert compra is not None
    compra.bloqueo_hasta = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    consultada = client.get(f"/api/v1/compras/{compra_id}")
    assert consultada.status_code == 200
    assert consultada.json()["estado"] == "vencida"
    assert consultada.json()["viajeros"][0]["tiquetes"][0]["estado"] == "vencido"

    confirmar = client.post(f"/api/v1/compras/{compra_id}/confirmar")
    assert confirmar.status_code == 409
    assert confirmar.json()["error"]["codigo"] == "bloqueo_vencido"

    soltar = client.delete(f"/api/v1/compras/{compra_id}")
    assert soltar.status_code == 204


def test_hu25_confirmar_una_compra_pagada_responde_estado_invalido(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: una compra ya pagada no se confirma ni se suelta (409 `estado_invalido`)."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_compra_pagada")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    _login(client, cliente)
    compra = client.post("/api/v1/compras", json=_cuerpo(vuelo)).json()
    assert client.post(f"/api/v1/compras/{compra['id']}/confirmar").status_code == 200

    confirmar = client.post(f"/api/v1/compras/{compra['id']}/confirmar")
    assert confirmar.status_code == 409
    assert confirmar.json()["error"] == {
        "codigo": "estado_invalido",
        "mensaje": "La compra ya está pagada.",
    }

    soltar = client.delete(f"/api/v1/compras/{compra['id']}")
    assert soltar.status_code == 409
    assert soltar.json()["error"]["codigo"] == "estado_invalido"


def test_hu25_un_correo_sin_verificar_no_puede_comprar(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · HU-02: con el correo sin verificar, POST /compras responde 403 y no bloquea

    sillas.
    """
    cliente = cliente_con_perfil(
        db, crear_usuario, verificado=False, nombre_usuario="api_compra_sin_verificar"
    )
    vuelo = crear_vuelo(db, salida=SALIDA)
    _login(client, cliente)

    respuesta = client.post("/api/v1/compras", json=_cuerpo(vuelo))

    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == {
        "codigo": "correo_no_verificado",
        "mensaje": "Verifica tu correo para reservar o comprar.",
    }


def test_hu25_el_limite_de_cinco_responde_por_la_api(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RF-33: el sexto tiquete activo responde `limite_tiquetes` por la API."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_compra_limite")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _login(client, cliente)
    cinco = [
        viajero(f"10203046{indice:02d}", email=f"api{indice}@example.com") for indice in range(5)
    ]
    primera = client.post(
        "/api/v1/compras",
        json=entrada([vuelo], cinco).model_dump(mode="json"),
    )
    assert primera.status_code == 201

    sexta = client.post("/api/v1/compras", json=_cuerpo(vuelo))

    assert sexta.status_code == 409
    assert sexta.json()["error"]["codigo"] == "limite_tiquetes"
    assert sexta.json()["error"]["mensaje"] == (
        "Un cliente puede tener máximo 5 tiquetes activos en el mismo vuelo."
    )


def test_hu25_comprar_dos_veces_no_duplica_sillas_ni_movimientos(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RNF-17: dos confirmaciones de la misma compra solo cobran una vez."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_compra_doble")
    vuelo = crear_vuelo(db, salida=SALIDA, precio_economica=800_000)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    _login(client, cliente)
    compra = client.post("/api/v1/compras", json=_cuerpo(vuelo)).json()

    assert client.post(f"/api/v1/compras/{compra['id']}/confirmar").status_code == 200
    segunda = client.post(f"/api/v1/compras/{compra['id']}/confirmar")

    assert segunda.status_code == 409
    assert monedero_service.saldo_de(db, cliente.id) == 200_000
    compras = list(db.scalars(select(Transaccion).where(Transaccion.cliente_id == cliente.id)))
    assert len(compras) == 1
    debitos = list(
        db.scalars(
            select(Movimiento).where(
                Movimiento.cliente_id == cliente.id, Movimiento.tipo == "compra"
            )
        )
    )
    assert len(debitos) == 1
    assert debitos[0].valor == -800_000
