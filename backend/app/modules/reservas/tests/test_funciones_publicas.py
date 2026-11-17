"""Funciones públicas del módulo reservas (HU-09, HU-15, HU-16, HU-18, HU-22)."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.reservas import service
from app.modules.reservas.models import Tiquete, Tramo
from app.modules.reservas.tests.fabricas import (
    crear_compra,
    crear_reserva,
    crear_tiquete,
    crear_tramo,
    crear_transaccion,
    crear_viajero,
)
from app.modules.vuelos import service as vuelos_service
from app.modules.vuelos.schemas import VueloEntrada
from app.modules.vuelos.tests.fabricas import crear_vuelo

SALIDA = datetime(2099, 1, 15, 10, 0, tzinfo=UTC)


def test_ocupacion_cuenta_vendidas_reservadas_y_reservas_activas(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-15, HU-16, HU-18 · RF-32: la ocupación separa vendidas y reservadas por clase,
    cuenta las reservas vigentes y no cuenta los tiquetes cancelados o vencidos."""
    cliente_uno = crear_usuario(
        Rol.CLIENTE, nombre_usuario="cliente_ocu_uno", email="ocu1@example.com"
    )
    cliente_dos = crear_usuario(
        Rol.CLIENTE, nombre_usuario="cliente_ocu_dos", email="ocu2@example.com"
    )
    vuelo = crear_vuelo(db, salida=SALIDA)
    vuelo_sin_ventas = crear_vuelo(db, salida=SALIDA, origen="BOG", destino="MDE")

    # Reserva vigente con una silla en cada clase.
    reserva = crear_transaccion(db, cliente_uno.id, tipo="reserva", estado="vigente")
    tramo_reserva_e = crear_tramo(db, reserva, vuelo, clase="economica")
    tramo_reserva_p = crear_tramo(db, reserva, vuelo, clase="primera")
    crear_tiquete(
        db,
        tramo_reserva_e,
        crear_viajero(db, reserva),
        vuelo=vuelo,
        estado="reservado",
    )
    crear_tiquete(
        db,
        tramo_reserva_p,
        crear_viajero(db, reserva),
        vuelo=vuelo,
        estado="reservado",
    )

    # Compra con tres sillas en económica y una en primera.
    compra = crear_transaccion(db, cliente_dos.id, tipo="compra", estado="pagada")
    tramo_compra_e = crear_tramo(db, compra, vuelo, clase="economica")
    tramo_compra_p = crear_tramo(db, compra, vuelo, clase="primera")
    for _ in range(3):
        crear_tiquete(
            db,
            tramo_compra_e,
            crear_viajero(db, compra),
            vuelo=vuelo,
            estado="comprado",
        )
    crear_tiquete(
        db,
        tramo_compra_p,
        crear_viajero(db, compra),
        vuelo=vuelo,
        estado="comprado",
    )

    # Reserva vencida y reserva cancelada: sus tiquetes ya no ocupan silla.
    vencida = crear_transaccion(db, cliente_uno.id, tipo="reserva", estado="vencida")
    tramo_vencida = crear_tramo(db, vencida, vuelo)
    crear_tiquete(
        db,
        tramo_vencida,
        crear_viajero(db, vencida),
        vuelo=vuelo,
        estado="vencido",
    )
    cancelada = crear_transaccion(db, cliente_uno.id, tipo="reserva", estado="cancelada")
    tramo_cancelada = crear_tramo(db, cancelada, vuelo)
    crear_tiquete(
        db,
        tramo_cancelada,
        crear_viajero(db, cancelada),
        vuelo=vuelo,
        estado="cancelado",
    )

    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id, vuelo_sin_ventas.id])

    assert ocupacion[vuelo.id].vendidas_economica == 3
    assert ocupacion[vuelo.id].vendidas_primera == 1
    assert ocupacion[vuelo.id].reservadas_economica == 1
    assert ocupacion[vuelo.id].reservadas_primera == 1
    assert ocupacion[vuelo.id].reservas_activas == 1
    assert ocupacion[vuelo.id].tiquetes_vendidos == 4
    assert ocupacion[vuelo_sin_ventas.id] == service.OcupacionVuelo()


def test_pasajeros_de_vuelo_solo_incluye_tiquetes_comprados(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-18: el detalle de pasajeros trae solo tiquetes comprados, con clase y silla."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_pasajeros")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra = crear_transaccion(db, cliente.id, tipo="compra", estado="pagada")
    tramo_e = crear_tramo(db, compra, vuelo, clase="economica")
    tramo_p = crear_tramo(db, compra, vuelo, clase="primera")
    crear_tiquete(
        db,
        tramo_e,
        crear_viajero(db, compra, nombres="Ana", apellidos="Pérez"),
        vuelo=vuelo,
        estado="comprado",
    )
    crear_tiquete(
        db,
        tramo_p,
        crear_viajero(
            db, compra, nombres="Luis", apellidos="Mora", fecha_nacimiento=date(1980, 1, 1)
        ),
        vuelo=vuelo,
        estado="comprado",
    )
    crear_reserva(db, cliente.id, vuelo, cantidad=1)

    pasajeros = service.pasajeros_de_vuelo(db, vuelo.id)

    assert [(p.nombres, p.apellidos, p.clase) for p in pasajeros] == [
        ("Luis", "Mora", "primera"),
        ("Ana", "Pérez", "economica"),
    ]
    assert all(p.numero_silla > 0 for p in pasajeros)


def test_tiquetes_activos_en_vuelo_cuenta_solo_los_del_cliente(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-32 · HU-22: el carrito cuenta compras y reservas del cliente en el vuelo y no
    cuenta los tiquetes de otro cliente ni los cancelados."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_activos")
    otro = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_otro")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_compra(db, cliente.id, vuelo, cantidad=3)
    crear_reserva(db, cliente.id, vuelo, cantidad=2)
    crear_compra(db, otro.id, vuelo, cantidad=1)

    assert service.tiquetes_activos_en_vuelo(db, cliente.id, vuelo.id) == 5
    assert service.tiquetes_activos_en_vuelo(db, otro.id, vuelo.id) == 1

    tiquete = db.scalar(select(Tiquete).where(Tiquete.vuelo_id == vuelo.id).order_by(Tiquete.id))
    assert tiquete is not None
    tiquete.estado = "cancelado"
    db.flush()
    assert service.tiquetes_activos_en_vuelo(db, cliente.id, vuelo.id) == 4


def test_tiquetes_activos_futuros_deduplica_por_transaccion_y_vuelo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-09: Mis viajes devuelve una entrada por transacción y vuelo, solo de vuelos que no
    han salido y con tiquetes activos."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_futuros")
    vuelo = crear_vuelo(db, salida=SALIDA)
    vuelo_pasado = crear_vuelo(
        db,
        salida=datetime(2020, 1, 1, 10, 0, tzinfo=UTC),
        origen="BOG",
        destino="MDE",
    )
    compra = crear_compra(db, cliente.id, vuelo, cantidad=2, codigo="ABC123")
    reserva = crear_reserva(db, cliente.id, vuelo, cantidad=2)
    crear_compra(db, cliente.id, vuelo_pasado, cantidad=1)

    cancelada = crear_compra(db, cliente.id, vuelo, cantidad=1)
    tiquete_cancelado = db.scalar(
        select(Tiquete)
        .join(Tramo, Tiquete.tramo_id == Tramo.id)
        .where(Tramo.transaccion_id == cancelada.id)
    )
    assert tiquete_cancelado is not None
    tiquete_cancelado.estado = "cancelado"
    db.flush()

    activos = service.tiquetes_activos_futuros_de_cliente(db, cliente.id)

    assert len(activos) == 2
    codigos = {tiquete.codigo_reserva for tiquete in activos}
    assert codigos == {"ABC123", None}
    assert {tiquete.tipo for tiquete in activos} == {"compra", "reserva"}
    assert all(tiquete.vuelo_codigo == vuelo.codigo for tiquete in activos)
    assert all(tiquete.origen == "Pereira" for tiquete in activos)
    assert all(tiquete.destino == "Bogotá" for tiquete in activos)
    assert activos[0].salida <= activos[1].salida
    assert compra.id != reserva.id


def test_una_reserva_activa_impide_editar_el_vuelo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-15 · RF-18: con una reserva vigente, editar el vuelo responde
    `vuelo_con_reservas` y no cambia nada."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_edicion")
    admin = crear_usuario(Rol.ADMIN, nombre_usuario="admin_edicion")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_reserva(db, cliente.id, vuelo, cantidad=1)
    precio = vuelo.precio_economica

    datos = VueloEntrada(
        origen="PEI",
        destino="BOG",
        fecha_salida=date(2099, 1, 15),
        hora_salida=time(10, 0),
        precio_economica=precio + 1,
        precio_primera=vuelo.precio_primera + 1,
    )
    with pytest.raises(vuelos_service.VueloConReservas) as error:
        vuelos_service.editar_vuelo(db, vuelo.id, datos, usuario_id=admin.id)

    assert error.value.codigo == "vuelo_con_reservas"
    assert vuelo.precio_economica == precio
