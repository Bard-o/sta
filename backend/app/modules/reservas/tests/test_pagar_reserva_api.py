"""API de pagar una reserva y de Mis viajes (HU-27, RF-35, RF-38, RF-45, RNF-17).

Los vuelos salen dentro de 30 días porque los endpoints usan la hora real.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.testing import CONTRASENA_TEST
from app.modules.monedero import service as monedero_service
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas.tests.apoyo import cliente_verificado, entrada, viajero
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import crear_vuelo

P = 280_000


def _login(client: TestClient, usuario: object) -> None:
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200


def _vuelo(db: Session, dias: int = 30, **cambios: Any) -> Vuelo:
    return crear_vuelo(db, salida=datetime.now(UTC) + timedelta(days=dias), **cambios)


def _reservar(client: TestClient, vuelo: Vuelo, viajeros: list[dict[str, Any]]) -> dict[str, Any]:
    respuesta = client.post(
        "/api/v1/reservas", json=entrada([vuelo], viajeros).model_dump(mode="json")
    )
    assert respuesta.status_code == 201
    return respuesta.json()


def _dos_viajeros() -> list[dict[str, Any]]:
    return [
        viajero("1020305001", nombres="Uno", email="uno@example.com"),
        viajero("1020305002", nombres="Dos", email="dos@example.com"),
    ]


def test_hu27_flujo_de_pago_por_la_api(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27: POST /reservas/{id}/pagar paga un viajero, devuelve reserva y compra con el mismo

    código, Mis viajes las lista en sus pestañas y un segundo pago deja la reserva `pagada`.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_paga_flujo")
    vuelo = _vuelo(db)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    _login(client, cliente)
    reserva = _reservar(client, vuelo, _dos_viajeros())
    primero = reserva["viajeros"][0]["id"]

    pago = client.post(f"/api/v1/reservas/{reserva['id']}/pagar", json={"viajero_ids": [primero]})

    assert pago.status_code == 200
    cuerpo = pago.json()
    assert set(cuerpo) == {"reserva", "compra"}
    en_reserva, compra = cuerpo["reserva"], cuerpo["compra"]
    assert en_reserva["id"] == reserva["id"]
    assert en_reserva["tipo"] == "reserva"
    assert en_reserva["estado"] == "vigente"
    assert en_reserva["compra_id"] == compra["id"]
    assert en_reserva["reserva_id"] is None
    assert en_reserva["vence_en"] == reserva["vence_en"]
    assert en_reserva["total"] == 2 * P
    assert en_reserva["total_pendiente"] == P
    assert compra["tipo"] == "compra"
    assert compra["codigo"] == reserva["codigo"]
    assert compra["reserva_id"] == reserva["id"]
    assert compra["compra_id"] is None
    assert compra["estado"] == "activa"
    assert compra["total"] == P
    assert compra["total_pendiente"] == 0
    assert compra["vence_en"] is None
    assert compra["pagada_en"] is not None
    assert [v["id"] for v in compra["viajeros"]] == [primero]
    assert compra["viajeros"][0]["tiquetes"][0]["estado"] == "comprado"
    assert monedero_service.saldo_de(db, cliente.id) == 1_000_000 - P

    compras = client.get("/api/v1/mis-viajes", params={"tipo": "compra"})
    assert compras.status_code == 200
    assert [item["id"] for item in compras.json()["items"]] == [compra["id"]]
    reservas = client.get("/api/v1/mis-viajes", params={"tipo": "reserva"})
    assert [(item["id"], item["compra_id"]) for item in reservas.json()["items"]] == [
        (reserva["id"], compra["id"])
    ]
    consultada = client.get(f"/api/v1/compras/{compra['id']}")
    assert consultada.status_code == 200
    assert consultada.json()["estado"] == "activa"

    resto = client.post(f"/api/v1/reservas/{reserva['id']}/pagar", json={})

    assert resto.status_code == 200
    assert resto.json()["reserva"]["estado"] == "pagada"
    assert resto.json()["reserva"]["total_pendiente"] == 0
    assert resto.json()["compra"]["id"] == compra["id"]
    assert resto.json()["compra"]["total"] == 2 * P
    assert len(resto.json()["compra"]["viajeros"]) == 2
    assert monedero_service.saldo_de(db, cliente.id) == 1_000_000 - 2 * P


def test_hu27_los_errores_del_pago_usan_el_formato_unico(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RNF-17: reserva inexistente, viajero ajeno, menor solo, saldo insuficiente,

    reserva ya pagada y correo sin verificar responden el formato único con su código.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_paga_errores")
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    _login(client, cliente)
    con_menor = _reservar(
        client,
        _vuelo(db),
        [
            viajero("1020305101", nombres="Adulto", email="adulto@example.com"),
            viajero(
                "1020305102",
                nombres="Menor",
                fecha_nacimiento=date(2015, 1, 1),
                email="menor@example.com",
            ),
        ],
    )
    cara = _reservar(
        client,
        _vuelo(db, dias=31, precio_economica=3_000_000),
        [viajero("1020305103", email="cara@example.com")],
    )
    adulto, menor = (v["id"] for v in con_menor["viajeros"])

    inexistente = client.post("/api/v1/reservas/999999/pagar", json={})
    assert inexistente.status_code == 404
    assert inexistente.json()["error"] == {
        "codigo": "no_encontrado",
        "mensaje": "La reserva no existe.",
    }

    ajeno = client.post(
        f"/api/v1/reservas/{con_menor['id']}/pagar",
        json={"viajero_ids": [cara["viajeros"][0]["id"]]},
    )
    assert ajeno.status_code == 422
    assert ajeno.json()["error"]["codigo"] == "datos_invalidos"
    assert ajeno.json()["error"]["campos"] == {
        "viajero_ids": "Elige viajeros de esta reserva que sigan sin pagar."
    }

    solo_menor = client.post(
        f"/api/v1/reservas/{con_menor['id']}/pagar", json={"viajero_ids": [menor]}
    )
    assert solo_menor.status_code == 422
    assert solo_menor.json()["error"]["codigo"] == "menor_sin_adulto"
    assert solo_menor.json()["error"]["campos"] == {
        "viajero_ids": "Paga también a un adulto: un menor no puede quedar solo en la compra."
    }

    sin_saldo = client.post(f"/api/v1/reservas/{cara['id']}/pagar", json={})
    assert sin_saldo.status_code == 409
    assert sin_saldo.json()["error"]["codigo"] == "saldo_insuficiente"
    assert "te faltan $ 2.000.000" in sin_saldo.json()["error"]["mensaje"]
    assert monedero_service.saldo_de(db, cliente.id) == 1_000_000

    pagada = client.post(
        f"/api/v1/reservas/{con_menor['id']}/pagar", json={"viajero_ids": [adulto, menor]}
    )
    assert pagada.status_code == 200
    de_nuevo = client.post(f"/api/v1/reservas/{con_menor['id']}/pagar", json={})
    assert de_nuevo.status_code == 409
    assert de_nuevo.json()["error"]["codigo"] == "reserva_no_vigente"
    assert de_nuevo.json()["error"]["mensaje"] == (
        "La reserva ya no está vigente: venció, se canceló o ya está pagada."
    )

    cliente.email_verificado = False
    db.flush()
    sin_verificar = client.post(f"/api/v1/reservas/{cara['id']}/pagar", json={})
    assert sin_verificar.status_code == 403
    assert sin_verificar.json()["error"]["codigo"] == "correo_no_verificado"


def test_rf45_mis_viajes_por_la_api(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-45: GET /mis-viajes responde la página con su paginación, cada cliente ve lo

    suyo, un rango al revés es `rango_invalido` y falta el `tipo` es `datos_invalidos`.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_viajes_dueno")
    otro = cliente_verificado(db, crear_usuario, nombre_usuario="api_viajes_otro")
    _login(client, cliente)
    reserva = _reservar(client, _vuelo(db), [viajero("1020305201", email="uno@example.com")])

    pagina = client.get("/api/v1/mis-viajes", params={"tipo": "reserva"})

    assert pagina.status_code == 200
    cuerpo = pagina.json()
    assert set(cuerpo) == {"items", "total", "pagina", "por_pagina"}
    assert (cuerpo["total"], cuerpo["pagina"], cuerpo["por_pagina"]) == (1, 1, 20)
    assert cuerpo["items"][0]["id"] == reserva["id"]
    assert cuerpo["items"][0]["estado"] == "vigente"
    assert cuerpo["items"][0]["viajeros"][0]["tiquetes"][0]["estado"] == "reservado"
    sin_compras = client.get("/api/v1/mis-viajes", params={"tipo": "compra"})
    assert sin_compras.json()["items"] == []
    assert sin_compras.json()["total"] == 0

    _login(client, otro)
    ajeno = client.get("/api/v1/mis-viajes", params={"tipo": "reserva"})
    assert ajeno.status_code == 200
    assert ajeno.json()["total"] == 0
    assert ajeno.json()["items"] == []

    al_reves = client.get(
        "/api/v1/mis-viajes",
        params={"tipo": "reserva", "desde": "2027-01-10", "hasta": "2027-01-01"},
    )
    assert al_reves.status_code == 422
    assert al_reves.json()["error"]["codigo"] == "rango_invalido"
    assert "hasta" in al_reves.json()["error"]["campos"]

    sin_tipo = client.get("/api/v1/mis-viajes")
    assert sin_tipo.status_code == 422
    assert sin_tipo.json()["error"]["codigo"] == "datos_invalidos"
