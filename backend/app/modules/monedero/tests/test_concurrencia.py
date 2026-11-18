"""Concurrencia de las recargas del monedero con hilos y conexiones reales (RF-48, RNF-17).

Cada hilo hace lo mismo que `POST /monedero/recargas`: llama al service con su propia sesión y
confirma. La fixture `base_confirmada` (app/core/testing.py) da la sesión por hilo y borra lo
confirmado.
"""

from datetime import UTC, datetime
from functools import partial
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST, BaseConfirmada
from app.modules.monedero import service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.schemas import RecargaEntrada
from app.modules.monedero.tests.fabricas import crear_tarjeta
from app.modules.usuarios import service as usuarios_service

AHORA = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
RECARGAS = 10
VALOR = 50_000


def _cliente_sin_movimientos(sesion: Session, nombre: str) -> int:
    """Cliente verificado que todavía no tiene ningún movimiento."""
    cliente = usuarios_service.crear_usuario(
        sesion,
        nombre_usuario=nombre,
        contrasena=CONTRASENA_TEST,
        rol=Rol.CLIENTE,
        email=f"{nombre}@example.com",
        email_verificado=True,
    )
    return cliente.id


def _recargar(cliente_id: int, tarjeta_id: int, valor: int, sesion: Session) -> int:
    """`POST /monedero/recargas`: devuelve el saldo resultante que vio el cliente."""
    movimiento = service.recargar(
        sesion, cliente_id, RecargaEntrada(tarjeta_id=tarjeta_id, valor=valor), ahora=AHORA
    )
    sesion.commit()
    return movimiento.saldo_resultante


def _descuadres(sesion: Session, cliente_ids: list[int]) -> list[Any]:
    """RF-48: movimientos cuyo saldo resultante no es la suma acumulada de los movimientos."""
    acumulado = func.sum(Movimiento.valor).over(
        partition_by=Movimiento.cliente_id, order_by=Movimiento.id
    )
    filas = (
        select(
            Movimiento.id,
            Movimiento.cliente_id,
            Movimiento.saldo_resultante,
            acumulado.label("acumulado"),
        )
        .where(Movimiento.cliente_id.in_(cliente_ids))
        .subquery()
    )
    return list(
        sesion.execute(
            select(filas.c.id, filas.c.saldo_resultante, filas.c.acumulado)
            .where(filas.c.saldo_resultante != filas.c.acumulado)
            .order_by(filas.c.id)
        )
    )


def test_rf48_las_primeras_recargas_simultaneas_de_un_cliente_dejan_el_saldo_en_orden(
    base_confirmada: BaseConfirmada,
) -> None:
    """RF-48 · RNF-17: 10 recargas simultáneas de $ 50.000, las primeras de un cliente sin

    movimientos, se aprueban todas y el saldo resultante de cada movimiento es la suma
    acumulada: 50.000, 100.000, … 500.000, sin que dos recargas lean el mismo saldo.
    """
    with base_confirmada.sesion() as sesion:
        cliente_id = _cliente_sin_movimientos(sesion, "conc_primeras_recargas")
        tarjeta_id = crear_tarjeta(sesion, cliente_id).id
        sesion.commit()
        assert service.saldo_de(sesion, cliente_id) == 0

    resultados = base_confirmada.en_paralelo(
        [partial(_recargar, cliente_id, tarjeta_id, VALOR) for _ in range(RECARGAS)]
    )

    assert len(resultados) == RECARGAS
    with base_confirmada.sesion() as sesion:
        assert service.saldo_de(sesion, cliente_id) == RECARGAS * VALOR
        movimientos = sesion.scalars(
            select(Movimiento).where(Movimiento.cliente_id == cliente_id).order_by(Movimiento.id)
        ).all()
        assert [movimiento.tipo for movimiento in movimientos] == ["recarga"] * RECARGAS
        assert [movimiento.saldo_resultante for movimiento in movimientos] == [
            VALOR * orden for orden in range(1, RECARGAS + 1)
        ]
        # Lo que vio cada cliente en su respuesta tampoco se repite.
        assert sorted(resultados) == [VALOR * orden for orden in range(1, RECARGAS + 1)]
        # RF-48: el saldo resultante de cada movimiento es la suma acumulada.
        assert _descuadres(sesion, [cliente_id]) == []
