"""Interfaz pública del módulo monedero (HU-25, HU-28 a HU-31).

Aquí viven la validación de las tarjetas simuladas (RF-46, RNF-12), las funciones con las que
`reservas` cobra una compra y registra un reembolso (RF-39, RF-48) y las que usan los
endpoints de tarjetas, recargas, saldo y movimientos (HU-28 a HU-31).

Ninguna función hace commit: van en la transacción de quien llama (RNF-17).
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos, NoEncontrado
from app.modules.monedero import schemas
from app.modules.monedero.models import Franquicia, Movimiento, Tarjeta

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
    mes, anio = vencimiento.split("/")
    return _vencida(date(2000 + int(anio), int(mes), 1), ahora or datetime.now(UTC))


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


# ---------- Tarjetas del cliente (HU-28, HU-29) ----------


def listar_tarjetas(
    db: Session, usuario_id: int, *, ahora: datetime | None = None
) -> list[schemas.Tarjeta]:
    """Tarjetas no eliminadas del cliente, de la más reciente a la más antigua (HU-29).

    Incluye las vencidas con `vencida: true`, para que el cliente pueda eliminarlas.
    """
    momento = ahora or datetime.now(UTC)
    tarjetas = db.scalars(
        select(Tarjeta)
        .where(Tarjeta.cliente_id == usuario_id, Tarjeta.eliminada.is_(False))
        .order_by(Tarjeta.creado_en.desc(), Tarjeta.id.desc())
    ).all()
    return [_a_tarjeta(tarjeta, momento) for tarjeta in tarjetas]


def registrar_tarjeta(
    db: Session, usuario_id: int, datos: schemas.TarjetaEntrada, *, ahora: datetime | None = None
) -> schemas.Tarjeta:
    """Registra una tarjeta simulada con Luhn y vencimiento (HU-28, RF-46).

    Guarda solo los últimos 4 dígitos y un token simulado: el número completo y el CVV se
    validan y se descartan (RNF-12). La misma tarjeta se puede registrar más de una vez.
    """
    momento = ahora or datetime.now(UTC)
    franquicia = validar_tarjeta(datos.numero, datos.vencimiento, ahora=momento)
    mes, anio = datos.vencimiento.split("/")

    tarjeta = Tarjeta(
        cliente_id=usuario_id,
        tipo=datos.tipo,
        franquicia=franquicia,
        titular=datos.titular,
        ultimos_4=datos.numero[-4:],
        token=secrets.token_hex(32),
        vencimiento=date(2000 + int(anio), int(mes), 1),
    )
    db.add(tarjeta)
    db.flush()
    return _a_tarjeta(tarjeta, momento)


def eliminar_tarjeta(db: Session, usuario_id: int, tarjeta_id: int) -> None:
    """Borra lógicamente una tarjeta del cliente (HU-29, RF-46).

    La tarjeta deja de aparecer y de servir para recargar; las recargas hechas con ella
    conservan su referencia (`**** 1234`). Si no existe, es de otro cliente o ya se eliminó,
    lanza `no_encontrado` (404). No hace commit.
    """
    tarjeta = _obtener_tarjeta(db, usuario_id, tarjeta_id)
    tarjeta.eliminada = True
    db.flush()


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


# ---------- Recargas y movimientos (HU-30, HU-31) ----------


def recargar(
    db: Session, usuario_id: int, datos: schemas.RecargaEntrada, *, ahora: datetime | None = None
) -> schemas.Movimiento:
    """Recarga simulada desde una tarjeta vigente del cliente (HU-30, RF-47).

    La recarga se aprueba si la tarjeta es del cliente, no está eliminada y no está vencida.
    Registra un movimiento `recarga` con la referencia `**** 1234` y el saldo resultante.
    Bloquea los movimientos del cliente para que el saldo resultante quede en orden (RNF-17).
    No hace commit.
    """
    momento = ahora or datetime.now(UTC)
    tarjeta = _obtener_tarjeta(db, usuario_id, datos.tarjeta_id)
    if _vencida(tarjeta.vencimiento, momento):
        raise TarjetaVencida(
            campos={"tarjeta_id": "La tarjeta está vencida. Elige otra o registra una nueva."}
        )

    _bloquear_movimientos(db, usuario_id)
    movimiento = _registrar_movimiento(
        db,
        usuario_id,
        tipo="recarga",
        valor=datos.valor,
        saldo_resultante=saldo_de(db, usuario_id) + datos.valor,
        referencia=_enmascarada(tarjeta.ultimos_4),
    )
    return _a_movimiento(movimiento)


def listar_movimientos(
    db: Session,
    usuario_id: int,
    *,
    tipo: schemas.TipoMovimiento | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    pagina: int = 1,
    por_pagina: int = 20,
) -> schemas.PaginaMovimientos:
    """Movimientos del cliente, del más reciente al más antiguo (HU-31, RF-48).

    Filtra por `tipo` y por la fecha del movimiento en hora de Colombia: `desde` y `hasta`
    incluyen el día completo. `total` cuenta los movimientos que pasan los filtros.
    """
    if desde is not None and hasta is not None and hasta < desde:
        raise DatosInvalidos(
            "Revisa los rangos marcados.",
            codigo="rango_invalido",
            campos={"hasta": "La fecha final no puede ser anterior a la inicial."},
        )

    filtros = [Movimiento.cliente_id == usuario_id]
    if tipo is not None:
        filtros.append(Movimiento.tipo == tipo)
    if desde is not None:
        filtros.append(Movimiento.creado_en >= _inicio_del_dia(desde))
    if hasta is not None:
        filtros.append(Movimiento.creado_en < _inicio_del_dia(hasta + timedelta(days=1)))

    total = db.scalar(select(func.count()).select_from(Movimiento).where(*filtros)) or 0
    filas = db.scalars(
        select(Movimiento)
        .where(*filtros)
        .order_by(Movimiento.creado_en.desc(), Movimiento.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return schemas.PaginaMovimientos(
        items=[_a_movimiento(movimiento) for movimiento in filas],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
    )


def _obtener_tarjeta(db: Session, usuario_id: int, tarjeta_id: int) -> Tarjeta:
    """Tarjeta no eliminada del cliente. Si no existe, es de otro o ya se eliminó: 404."""
    tarjeta = db.scalar(
        select(Tarjeta).where(
            Tarjeta.id == tarjeta_id,
            Tarjeta.cliente_id == usuario_id,
            Tarjeta.eliminada.is_(False),
        )
    )
    if tarjeta is None:
        raise NoEncontrado("La tarjeta no existe.")
    return tarjeta


def _a_tarjeta(tarjeta: Tarjeta, ahora: datetime) -> schemas.Tarjeta:
    """Tarjeta del contrato: enmascarada y con su vencimiento en `MM/AA`."""
    return schemas.Tarjeta(
        id=tarjeta.id,
        tipo=tarjeta.tipo,
        franquicia=tarjeta.franquicia,
        titular=tarjeta.titular,
        numero_enmascarado=_enmascarada(tarjeta.ultimos_4),
        vencimiento=f"{tarjeta.vencimiento.month:02d}/{tarjeta.vencimiento.year % 100:02d}",
        vencida=_vencida(tarjeta.vencimiento, ahora),
        creada_en=tarjeta.creado_en,
    )


def _a_movimiento(movimiento: Movimiento | MovimientoMonedero) -> schemas.Movimiento:
    return schemas.Movimiento(
        id=movimiento.id,
        tipo=movimiento.tipo,
        valor=movimiento.valor,
        saldo_resultante=movimiento.saldo_resultante,
        referencia=movimiento.referencia,
        creado_en=movimiento.creado_en,
    )


def _vencida(vencimiento: date, ahora: datetime) -> bool:
    """La tarjeta pasó su mes de vencimiento, en hora de Colombia (HU-28)."""
    actual = ahora.astimezone(_ZONA_NEGOCIO)
    return (vencimiento.year, vencimiento.month) < (actual.year, actual.month)


def _enmascarada(ultimos_4: str) -> str:
    """RNF-12: `****` y los últimos 4 dígitos, como se muestra y se guarda en la referencia."""
    return f"**** {ultimos_4}"


def _inicio_del_dia(fecha: date) -> datetime:
    """Medianoche de `fecha` en hora de Colombia, en UTC (filtros de HU-31)."""
    return datetime.combine(fecha, time.min, tzinfo=_ZONA_NEGOCIO).astimezone(UTC)


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
