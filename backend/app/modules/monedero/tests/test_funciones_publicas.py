"""Funciones públicas del monedero (HU-25, HU-31, RF-48)."""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.monedero import service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.fabricas import crear_movimiento


def _cliente(crear_usuario: Callable[..., Any], nombre: str) -> Any:
    return crear_usuario(Rol.CLIENTE, nombre_usuario=nombre, email=f"{nombre}@example.com")


def _movimientos(db: Session, cliente_id: int) -> list[Movimiento]:
    return list(
        db.scalars(
            select(Movimiento).where(Movimiento.cliente_id == cliente_id).order_by(Movimiento.id)
        ).all()
    )


def test_hu25_debitar_descuenta_y_registra_el_movimiento(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: con $ 1.000.000, debitar $ 800.000 deja el saldo en $ 200.000.

    El movimiento queda registrado como compra, con su saldo resultante y su referencia.
    """
    cliente = _cliente(crear_usuario, "cliente_debito")
    crear_movimiento(db, cliente.id, tipo="recarga", valor=1_000_000, saldo_resultante=1_000_000)

    movimiento = service.debitar(db, cliente.id, 800_000, referencia="ABC123")

    assert service.saldo_de(db, cliente.id) == 200_000
    assert movimiento.tipo == "compra"
    assert movimiento.valor == -800_000
    assert movimiento.saldo_resultante == 200_000
    assert movimiento.referencia == "ABC123"

    guardado = db.scalars(select(Movimiento).where(Movimiento.id == movimiento.id)).one()
    assert guardado.valor == -800_000
    assert guardado.saldo_resultante == 200_000


def test_hu25_sin_saldo_lanza_saldo_insuficiente_y_no_registra(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: con $ 500.000, debitar $ 800.000 lanza `saldo_insuficiente` y no registra nada."""
    cliente = _cliente(crear_usuario, "cliente_sin_saldo")
    crear_movimiento(db, cliente.id, tipo="recarga", valor=500_000, saldo_resultante=500_000)

    with pytest.raises(service.SaldoInsuficiente) as exc:
        service.debitar(db, cliente.id, 800_000, referencia="ABC123")

    assert exc.value.status_code == 409
    assert exc.value.codigo == "saldo_insuficiente"
    assert exc.value.mensaje == "Tu saldo no alcanza: te faltan $ 300.000."
    assert service.saldo_de(db, cliente.id) == 500_000
    assert len(_movimientos(db, cliente.id)) == 1


def test_rf48_el_saldo_nunca_queda_negativo(db: Session, crear_usuario: Callable[..., Any]) -> None:
    """RF-48: un segundo débito que no cabe en el saldo se rechaza y lo deja intacto."""
    cliente = _cliente(crear_usuario, "cliente_negativo")
    crear_movimiento(db, cliente.id, tipo="recarga", valor=500_000, saldo_resultante=500_000)

    service.debitar(db, cliente.id, 300_000, referencia="ABC123")
    with pytest.raises(service.SaldoInsuficiente):
        service.debitar(db, cliente.id, 300_000, referencia="ABC124")

    assert service.saldo_de(db, cliente.id) == 200_000
    assert all(movimiento.saldo_resultante >= 0 for movimiento in _movimientos(db, cliente.id))


def test_hu31_el_saldo_es_la_suma_de_los_movimientos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31, RF-48: el saldo es igual a la suma de todos los movimientos del cliente."""
    cliente = _cliente(crear_usuario, "cliente_suma")
    crear_movimiento(db, cliente.id, tipo="recarga", valor=500_000, saldo_resultante=500_000)
    crear_movimiento(db, cliente.id, tipo="compra", valor=-200_000, saldo_resultante=300_000)
    crear_movimiento(db, cliente.id, tipo="reembolso", valor=50_000, saldo_resultante=350_000)

    total = db.scalar(select(func.sum(Movimiento.valor)).where(Movimiento.cliente_id == cliente.id))
    ultimo = _movimientos(db, cliente.id)[-1]

    assert service.saldo_de(db, cliente.id) == 350_000
    assert total == 350_000
    assert ultimo.saldo_resultante == 350_000


def test_hu31_un_cliente_sin_movimientos_tiene_saldo_cero(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-31: un cliente sin movimientos ve saldo $ 0."""
    cliente = _cliente(crear_usuario, "cliente_vacio")

    assert service.saldo_de(db, cliente.id) == 0
    assert _movimientos(db, cliente.id) == []


def test_acreditar_registra_un_reembolso_y_suma_al_saldo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-48: un reembolso suma al saldo con su saldo resultante (iteración 3)."""
    cliente = _cliente(crear_usuario, "cliente_reembolso")
    crear_movimiento(db, cliente.id, tipo="recarga", valor=100_000, saldo_resultante=100_000)

    movimiento = service.acreditar(db, cliente.id, 50_000, referencia="Q8W2RT")

    assert movimiento.tipo == "reembolso"
    assert movimiento.valor == 50_000
    assert movimiento.saldo_resultante == 150_000
    assert service.saldo_de(db, cliente.id) == 150_000


def test_saldo_de_no_mezcla_clientes(db: Session, crear_usuario: Callable[..., Any]) -> None:
    """RF-48: cada cliente tiene su propio saldo."""
    uno = _cliente(crear_usuario, "cliente_monedero_uno")
    dos = _cliente(crear_usuario, "cliente_monedero_dos")
    crear_movimiento(db, uno.id, tipo="recarga", valor=500_000, saldo_resultante=500_000)
    crear_movimiento(db, dos.id, tipo="recarga", valor=250_000, saldo_resultante=250_000)

    assert service.saldo_de(db, uno.id) == 500_000
    assert service.saldo_de(db, dos.id) == 250_000


def test_debitar_rechaza_un_valor_no_positivo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-39: el valor de un débito debe ser mayor que 0."""
    cliente = _cliente(crear_usuario, "cliente_valor_cero")

    with pytest.raises(ValueError):
        service.debitar(db, cliente.id, 0, referencia="ABC123")

    assert _movimientos(db, cliente.id) == []
