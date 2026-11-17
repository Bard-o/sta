"""Interfaz pública del módulo monedero (HU-25, HU-28 a HU-31).

Aquí viven la validación de las tarjetas simuladas (RF-46, RNF-12) y las funciones con las
que `reservas` cobra una compra y registra un reembolso (RF-39, RF-48). Los endpoints son de
#119 y llaman a estas funciones.

Ninguna función hace commit: van en la transacción de quien llama (RNF-17).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos
from app.modules.monedero.models import Franquicia, Movimiento

# La tarjeta sirve hasta el último día de su mes de vencimiento, en hora de Colombia.
_ZONA_NEGOCIO = ZoneInfo("America/Bogota")


class SaldoInsuficiente(Conflicto):
    """RF-39: el saldo no alcanza para la compra; no se registra nada."""

    codigo = "saldo_insuficiente"
    mensaje = "Tu saldo no alcanza."


class TarjetaInvalida(DatosInvalidos):
    """RF-46: el número de la tarjeta no pasa el algoritmo de Luhn."""

    codigo = "tarjeta_invalida"
    mensaje = "Revisa los datos de la tarjeta."


class TarjetaVencida(DatosInvalidos):
    """RF-46: la tarjeta ya pasó su mes de vencimiento."""

    codigo = "tarjeta_vencida"
    mensaje = "Revisa los datos de la tarjeta."


@dataclass(frozen=True)
class MovimientoMonedero:
    """Movimiento del monedero tal como lo consumen los demás módulos."""

    id: int
    tipo: Literal["recarga", "compra", "reembolso"]
    valor: int
    saldo_resultante: int
    referencia: str
    creado_en: datetime


# ---------- Validación de tarjetas (HU-28, RF-46, RNF-12) ----------


def luhn_valido(numero: str) -> bool:
    """Algoritmo de Luhn sobre un número de 13 a 19 dígitos (RF-46)."""
    if not numero.isdigit() or not 13 <= len(numero) <= 19:
        return False

    total = 0
    for posicion, digito in enumerate(reversed(numero)):
        valor = int(digito)
        if posicion % 2 == 1:
            valor *= 2
            if valor > 9:
                valor -= 9
        total += valor
    return total % 10 == 0


def franquicia_de(numero: str) -> Franquicia:
    """Deduce la franquicia a partir del número, según el contrato de HU-28."""
    if numero.startswith("4"):
        return "visa"
    if numero[:2] in {"51", "52", "53", "54", "55"}:
        return "mastercard"
    if 2221 <= int(numero[:4]) <= 2720:
        return "mastercard"
    if numero[:2] in {"34", "37"}:
        return "amex"
    if numero[:3] in {"300", "301", "302", "303", "304", "305"} or numero[:2] in {
        "36",
        "38",
    }:
        return "diners"
    return "otra"


def tarjeta_vencida(vencimiento: str, *, ahora: datetime | None = None) -> bool:
    """La tarjeta ya venció: `MM/AA`, en hora de Colombia (HU-28).

    Una tarjeta con vencimiento del mes en curso sigue sirviendo hasta su último día.
    """
    ahora = ahora or datetime.now(UTC)
    actual = ahora.astimezone(_ZONA_NEGOCIO)
    mes, anio = vencimiento.split("/")
    return (2000 + int(anio), int(mes)) < (actual.year, actual.month)


def validar_tarjeta(numero: str, vencimiento: str, *, ahora: datetime | None = None) -> Franquicia:
    """Valida el número con Luhn y el vencimiento; devuelve la franquicia (RF-46).

    El formato del número, del vencimiento y del CVV lo valida `TarjetaEntrada` en los
    schemas. El CVV se descarta y nunca llega aquí ni a la base (RNF-12).
    """
    if not luhn_valido(numero):
        raise TarjetaInvalida(campos={"numero": "El número no es válido. Revisa los dígitos."})
    if tarjeta_vencida(vencimiento, ahora=ahora):
        raise TarjetaVencida(campos={"vencimiento": "La tarjeta está vencida."})
    return franquicia_de(numero)


# ---------- Saldo y movimientos (HU-25, HU-30, HU-31, RF-48) ----------


def saldo_de(db: Session, usuario_id: int) -> int:
    """Saldo del cliente: la suma de sus movimientos, 0 si no tiene (RF-48)."""
    total = db.scalar(
        select(func.coalesce(func.sum(Movimiento.valor), 0)).where(
            Movimiento.cliente_id == usuario_id
        )
    )
    return int(total or 0)


def debitar(db: Session, usuario_id: int, valor: int, *, referencia: str) -> MovimientoMonedero:
    """Registra un movimiento `compra` por -valor con su saldo resultante (RF-39).

    Bloquea los movimientos del cliente (`SELECT … FOR UPDATE`) para que dos compras
    simultáneas no lo dejen en negativo. Si el saldo no alcanza, lanza `SaldoInsuficiente`
    sin registrar nada. `valor` debe ser mayor que 0. No hace commit.
    """
    if valor <= 0:
        raise ValueError("El valor del débito debe ser mayor que 0.")

    _bloquear_movimientos(db, usuario_id)
    saldo = saldo_de(db, usuario_id)
    if saldo < valor:
        raise SaldoInsuficiente(f"Tu saldo no alcanza: te faltan $ {_pesos(valor - saldo)}.")

    return _registrar_movimiento(
        db,
        usuario_id,
        tipo="compra",
        valor=-valor,
        saldo_resultante=saldo - valor,
        referencia=referencia,
    )


def acreditar(db: Session, usuario_id: int, valor: int, *, referencia: str) -> MovimientoMonedero:
    """Registra un movimiento `reembolso` por +valor con su saldo resultante.

    Se usa en la iteración 3 para devolver el dinero de una compra cancelada. Bloquea los
    movimientos del cliente para que el saldo resultante quede en orden. `valor` debe ser
    mayor que 0. No hace commit.
    """
    if valor <= 0:
        raise ValueError("El valor del crédito debe ser mayor que 0.")

    _bloquear_movimientos(db, usuario_id)
    saldo = saldo_de(db, usuario_id)
    return _registrar_movimiento(
        db,
        usuario_id,
        tipo="reembolso",
        valor=valor,
        saldo_resultante=saldo + valor,
        referencia=referencia,
    )


def _bloquear_movimientos(db: Session, usuario_id: int) -> None:
    """Bloquea las filas que respaldan el saldo del cliente hasta el fin de la transacción.

    El saldo no es una fila: es la suma de los movimientos. Bloquearlos, en orden de id para
    no generar interbloqueos, serializa los débitos y los créditos del mismo cliente. Un
    cliente sin movimientos tiene saldo 0, así que cualquier débito falla y no hay riesgo de
    dejarlo en negativo.
    """
    db.execute(
        select(Movimiento.id)
        .where(Movimiento.cliente_id == usuario_id)
        .order_by(Movimiento.id)
        .with_for_update()
    ).all()


def _registrar_movimiento(
    db: Session,
    usuario_id: int,
    *,
    tipo: Literal["recarga", "compra", "reembolso"],
    valor: int,
    saldo_resultante: int,
    referencia: str,
) -> MovimientoMonedero:
    movimiento = Movimiento(
        cliente_id=usuario_id,
        tipo=tipo,
        valor=valor,
        saldo_resultante=saldo_resultante,
        referencia=referencia,
    )
    db.add(movimiento)
    db.flush()
    return MovimientoMonedero(
        id=movimiento.id,
        tipo=tipo,
        valor=valor,
        saldo_resultante=saldo_resultante,
        referencia=referencia,
        creado_en=movimiento.creado_en,
    )


def _pesos(valor: int) -> str:
    """COP con separador de miles de punto, como en la interfaz (IU-06)."""
    return f"{valor:,}".replace(",", ".")
