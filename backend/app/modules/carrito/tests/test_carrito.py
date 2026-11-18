"""HU-23: revisar el carrito y sus avisos (RF-30, SUP-07, SUP-15)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.carrito import service
from app.modules.carrito.tests.apoyo import (
    RUTA_CARRITO,
    agregar,
    crear_cliente,
    entrar,
    tramo,
)
from app.modules.carrito.tests.fabricas import crear_seleccion
from app.modules.vuelos.tests.fabricas import crear_promocion_bd, crear_vuelo

SALIDA = datetime(2027, 4, 15, 11, 0, tzinfo=UTC)


def test_hu23_avisa_el_precio_anterior_y_el_nuevo_cuando_cambia(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23 · RF-24: una promoción posterior se avisa con el precio anterior y el nuevo.

    El aviso no impide confirmar: se pagará el precio vigente.
    """
    cliente = crear_cliente(db, crear_usuario, "cliente_precio")
    vuelo = crear_vuelo(db, salida=SALIDA)
    cliente_http = entrar(client, cliente)
    creada = agregar(cliente_http, [tramo(vuelo.id)], viajeros=2)
    assert creada.status_code == 201
    crear_promocion_bd(db, vuelo, porcentaje=20)

    carrito = cliente_http.get(RUTA_CARRITO).json()
    seleccion = carrito["selecciones"][0]
    tramo_carrito = seleccion["tramos"][0]

    assert tramo_carrito["precio_al_agregar"] == 280_000
    assert tramo_carrito["precio_unitario"] == 224_000
    assert tramo_carrito["promocion_porcentaje"] == 20
    assert seleccion["avisos"] == [
        {
            "codigo": "precio_cambio",
            "mensaje": ("El precio cambió de $ 280.000 a $ 224.000. Pagarás el precio nuevo."),
            "tramo": 0,
        }
    ]
    assert seleccion["confirmable"] is True
    assert seleccion["subtotal"] == 448_000


def test_hu23_una_seleccion_vigente_es_confirmable_y_sin_avisos(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: sin cambios, la selección no tiene avisos y se puede confirmar."""
    cliente = crear_cliente(db, crear_usuario, "cliente_vigente")
    vuelo = crear_vuelo(db, salida=SALIDA)
    cliente_http = entrar(client, cliente)
    agregar(cliente_http, [tramo(vuelo.id)], viajeros=2)

    seleccion = cliente_http.get(RUTA_CARRITO).json()["selecciones"][0]

    assert seleccion["avisos"] == []
    assert seleccion["confirmable"] is True
    assert seleccion["reserva_venceria_en"] is not None


def test_hu23_una_seleccion_sin_disponibilidad_no_es_confirmable(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23 · RF-33: si la clase se quedó sin sillas, informa y no permite confirmar."""
    cliente = crear_cliente(db, crear_usuario, "cliente_sin_sillas")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_economica=1)
    crear_seleccion(db, cliente.id, [vuelo], viajeros=2)
    cliente_http = entrar(client, cliente)

    seleccion = cliente_http.get(RUTA_CARRITO).json()["selecciones"][0]

    assert seleccion["tramos"][0]["disponibles"] == 1
    assert seleccion["avisos"] == [
        {
            "codigo": "clase_agotada",
            "mensaje": (
                "Ya no quedan sillas suficientes en económica. Cambia de clase o quita este vuelo."
            ),
            "tramo": 0,
        }
    ]
    assert seleccion["confirmable"] is False
    assert seleccion["reserva_venceria_en"] is None


@pytest.mark.parametrize("estado", ["cancelado", "realizado"])
def test_rf30_un_vuelo_cancelado_o_realizado_no_es_confirmable(
    estado: str, db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """RF-30 · HU-23: un vuelo cancelado o realizado se marca `vuelo_no_disponible`."""
    cliente = crear_cliente(db, crear_usuario, f"cliente_{estado}")
    vuelo = crear_vuelo(db, salida=SALIDA, estado=estado)
    crear_seleccion(db, cliente.id, [vuelo])
    cliente_http = entrar(client, cliente)

    seleccion = cliente_http.get(RUTA_CARRITO).json()["selecciones"][0]

    assert seleccion["avisos"] == [
        {
            "codigo": "vuelo_no_disponible",
            "mensaje": f"{vuelo.codigo} ya no está a la venta: se canceló o ya se realizó.",
            "tramo": 0,
        }
    ]
    assert seleccion["confirmable"] is False
    assert seleccion["reserva_venceria_en"] is None


def test_rf30_un_vuelo_que_paso_su_limite_de_venta_no_es_confirmable(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """SUP-07: un vuelo nacional que sale en media hora ya cerró su venta."""
    cliente = crear_cliente(db, crear_usuario, "cliente_plazo_carrito")
    vuelo = crear_vuelo(db, salida=datetime.now(UTC) + timedelta(minutes=30))
    crear_seleccion(db, cliente.id, [vuelo])
    cliente_http = entrar(client, cliente)

    seleccion = cliente_http.get(RUTA_CARRITO).json()["selecciones"][0]

    assert seleccion["avisos"] == [
        {
            "codigo": "fuera_de_plazo",
            "mensaje": f"La venta de {vuelo.codigo} ya cerró.",
            "tramo": 0,
        }
    ]
    assert seleccion["confirmable"] is False
    assert seleccion["reserva_venceria_en"] is None


def test_hu23_las_selecciones_van_de_la_mas_reciente_a_la_mas_antigua(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: la más reciente primero; en la misma transacción desempata el id."""
    cliente = crear_cliente(db, crear_usuario, "cliente_orden")
    viejo = crear_vuelo(db, salida=SALIDA)
    nuevo = crear_vuelo(
        db, origen="PEI", destino="MDE", salida=datetime(2027, 4, 15, 8, 0, tzinfo=UTC)
    )
    primera = crear_seleccion(
        db, cliente.id, [viejo], agregada_en=datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    )
    segunda = crear_seleccion(
        db, cliente.id, [nuevo], agregada_en=datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    )
    cliente_http = entrar(client, cliente)

    ids = [seleccion["id"] for seleccion in cliente_http.get(RUTA_CARRITO).json()["selecciones"]]

    assert ids == [segunda.id, primera.id]


def test_hu23_el_total_suma_solo_las_confirmables(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-23: `cantidad` cuenta todas las selecciones y `total` solo las confirmables."""
    cliente = crear_cliente(db, crear_usuario, "cliente_total")
    valido = crear_vuelo(db, salida=SALIDA)
    agotado = crear_vuelo(
        db,
        origen="PEI",
        destino="MDE",
        salida=datetime(2027, 4, 15, 8, 0, tzinfo=UTC),
        capacidad_economica=1,
    )
    cliente_http = entrar(client, cliente)
    assert agregar(cliente_http, [tramo(valido.id)], viajeros=2).status_code == 201
    crear_seleccion(db, cliente.id, [agotado], viajeros=2)

    carrito = cliente_http.get(RUTA_CARRITO).json()

    assert carrito["cantidad"] == 2
    assert carrito["total"] == 560_000
    confirmable = next(
        seleccion for seleccion in carrito["selecciones"] if seleccion["confirmable"]
    )
    assert confirmable["subtotal"] == 560_000


def test_hu23_reserva_venceria_en_usa_el_menor_entre_24_horas_y_el_limite(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """SUP-07: si se reservara ahora, vence a las 24 h o en el límite de venta más próximo.

    El caso de dos tramos usa el límite más cercano de los dos vuelos.
    """
    cliente = crear_cliente(db, crear_usuario, "cliente_vencimiento")
    ida = crear_vuelo(db, origen="PEI", destino="BOG", salida=SALIDA)
    regreso = crear_vuelo(
        db, origen="BOG", destino="PEI", salida=datetime(2027, 4, 16, 9, 0, tzinfo=UTC)
    )
    crear_seleccion(db, cliente.id, [ida, regreso])

    antes = service.obtener_carrito(db, cliente.id, ahora=datetime(2026, 11, 17, 12, 0, tzinfo=UTC))
    assert antes.selecciones[0].reserva_venceria_en == datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

    cerca_del_limite = service.obtener_carrito(
        db, cliente.id, ahora=datetime(2027, 4, 14, 12, 0, tzinfo=UTC)
    )
    assert cerca_del_limite.selecciones[0].reserva_venceria_en == datetime(
        2027, 4, 15, 10, 0, tzinfo=UTC
    )
