"""Fábricas de tarjetas y movimientos para los tests del monedero.

Crean filas directamente, sin pasar por los endpoints de #119, para preparar saldos y
estados sin depender de la capa HTTP.
"""

from datetime import date, datetime
from itertools import count

from sqlalchemy.orm import Session

from app.modules.monedero.models import (
    Franquicia,
    Movimiento,
    Tarjeta,
    TipoMovimiento,
    TipoTarjeta,
)

_TARJETAS = count(1)


def crear_tarjeta(
    db: Session,
    cliente_id: int,
    *,
    tipo: TipoTarjeta = "credito",
    franquicia: Franquicia = "visa",
    titular: str = "LAURA GOMEZ RIOS",
    ultimos_4: str = "4242",
    token: str | None = None,
    vencimiento: date = date(2028, 8, 1),
    eliminada: bool = False,
) -> Tarjeta:
    """Crea una tarjeta simulada del cliente; el token se genera si no se indica."""
    if token is None:
        token = f"token-simulado-{next(_TARJETAS):04d}"

    tarjeta = Tarjeta(
        cliente_id=cliente_id,
        tipo=tipo,
        franquicia=franquicia,
        titular=titular,
        ultimos_4=ultimos_4,
        token=token,
        vencimiento=vencimiento,
        eliminada=eliminada,
    )
    db.add(tarjeta)
    db.flush()
    return tarjeta


def crear_movimiento(
    db: Session,
    cliente_id: int,
    *,
    tipo: TipoMovimiento = "recarga",
    valor: int = 500_000,
    saldo_resultante: int = 500_000,
    referencia: str = "**** 4242",
    creado_en: datetime | None = None,
) -> Movimiento:
    """Crea un movimiento con su saldo resultante; `creado_en` se ajusta si se indica."""
    movimiento = Movimiento(
        cliente_id=cliente_id,
        tipo=tipo,
        valor=valor,
        saldo_resultante=saldo_resultante,
        referencia=referencia,
    )
    if creado_en is not None:
        movimiento.creado_en = creado_en
    db.add(movimiento)
    db.flush()
    return movimiento
