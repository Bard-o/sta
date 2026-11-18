"""API de pagar una reserva (HU-27, RF-35, RF-38, RNF-17).

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
