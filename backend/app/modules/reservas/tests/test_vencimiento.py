"""Vencimiento automático de reservas (HU-24, RF-37, RNF-18)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import CorreoEnCola
from app.modules.reservas import service
from app.modules.reservas.models import Tramo, Transaccion
from app.modules.reservas.tests.apoyo import (
    AHORA,
    SALIDA,
    cliente_verificado,
    entrada,
    tiquetes_de,
    viajero,
)
from app.modules.reservas.tests.fabricas import crear_compra, crear_reserva
from app.modules.vuelos.tests.fabricas import crear_vuelo


def _correos(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def test_rf37_vence_la_reserva_libera_las_sillas_y_avisa_al_cliente(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-37 · HU-24: al cumplirse las 24 horas la reserva queda vencida, sus sillas se

    liberan y el cliente recibe un correo en la cola. La tarea es idempotente.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_vence")
    vuelo = crear_vuelo(db, salida=SALIDA)
    reserva = service.crear_reserva(db, cliente.id, entrada([vuelo]), ahora=AHORA)
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_economica == 1

    anuladas = service.vencer_reservas(db, AHORA + timedelta(hours=24))

    assert anuladas == 1
    assert reserva.estado == "vencida"
    assert all(tiquete.estado == "vencido" for tiquete in tiquetes_de(db, reserva))
    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    assert ocupacion.reservadas_economica == 0
    assert ocupacion.reservas_activas == 0

    correos = _correos(db)
    assert len(correos) == 1
    assert correos[0].destinatario == cliente.email
    assert reserva.codigo is not None
    assert reserva.codigo in correos[0].asunto
    assert correos[0].estado == "pendiente"


def test_rf37_correr_dos_veces_no_cambia_nada_la_segunda(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-37 · RNF-18: la tarea procesa lo vencido y es idempotente."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_idempotente")
    vuelo = crear_vuelo(db, salida=SALIDA)
    service.crear_reserva(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    assert service.vencer_reservas(db, AHORA + timedelta(hours=25)) == 1
    assert service.vencer_reservas(db, AHORA + timedelta(hours=26)) == 0
    assert len(_correos(db)) == 1


def test_rf37_no_vence_una_reserva_que_todavia_vive(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-37: una reserva con plazo pendiente sigue vigente y sus sillas ocupadas."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_vigente")
    vuelo = crear_vuelo(db, salida=SALIDA)
    reserva = service.crear_reserva(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    assert service.vencer_reservas(db, AHORA + timedelta(hours=23)) == 0

    assert reserva.estado == "vigente"
    assert all(tiquete.estado == "reservado" for tiquete in tiquetes_de(db, reserva))
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_economica == 1
    assert _correos(db) == []


def test_rf37_una_reserva_cerca_del_vuelo_vence_en_el_limite_de_venta(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-37 · SUP-07: si la salida es en menos de 24 horas, el vencimiento es el límite

    de venta (1 hora antes en un vuelo nacional), no las 24 horas.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_limite")
    salida = AHORA + timedelta(hours=10)
    vuelo = crear_vuelo(db, salida=salida)
    reserva = service.crear_reserva(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    assert service.vencer_reservas(db, salida - timedelta(hours=2)) == 0
    assert reserva.estado == "vigente"

    assert service.vencer_reservas(db, salida - timedelta(hours=1)) == 1
    assert reserva.estado == "vencida"


def test_rf37_no_toca_reservas_ya_vencidas_ni_compras(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-37: solo procesa reservas `vigente`; una compra o una reserva ya vencida no se toca."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_otros")
    vuelo = crear_vuelo(db, salida=SALIDA)
    vencida = crear_reserva(
        db,
        cliente.id,
        vuelo,
        estado="vencida",
        vence_en=AHORA - timedelta(hours=1),
        estado_tiquete="vencido",
    )
    compra = crear_compra(
        db,
        cliente.id,
        vuelo,
        estado="pendiente",
        bloqueo_hasta=AHORA + timedelta(hours=1),
        estado_tiquete="bloqueado",
    )

    assert service.vencer_reservas(db, AHORA) == 0

    assert vencida.estado == "vencida"
    assert compra.estado == "pendiente"
    assert _correos(db) == []


def test_rf37_vence_todas_las_reservas_vencidas_de_una_vez(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-37 · RNF-18: una vuelta procesa todo lo vencido hasta `ahora`, de varios clientes."""
    uno = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_lote_uno")
    dos = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_lote_dos")
    vuelo = crear_vuelo(db, salida=SALIDA)
    service.crear_reserva(db, uno.id, entrada([vuelo]), ahora=AHORA)
    service.crear_reserva(
        db,
        dos.id,
        entrada([vuelo], [viajero("1020304099", email="dos@example.com")]),
        ahora=AHORA,
    )

    assert service.vencer_reservas(db, AHORA + timedelta(hours=24)) == 2

    correos = _correos(db)
    assert {correo.destinatario for correo in correos} == {uno.email, dos.email}
    tramos = list(db.scalars(select(Tramo)))
    transacciones = list(db.scalars(select(Transaccion)))
    assert len(tramos) == 2
    assert all(transaccion.estado == "vencida" for transaccion in transacciones)
