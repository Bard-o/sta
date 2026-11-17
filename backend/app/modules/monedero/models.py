"""Modelos del monedero (RF-46 a RF-48, RNF-12, SUP-21, SUP-22).

Una `Tarjeta` es la tarjeta simulada con la que el cliente recarga. Solo guarda los últimos
cuatro dígitos y un token simulado: el número completo y el CVV se validan y se descartan
(RNF-12).

Un `Movimiento` es cada cambio del saldo. `valor` lleva signo (positivo en recargas y
reembolsos, negativo en compras) y `saldo_resultante` es el saldo después de aplicarlo. El
saldo del cliente es la suma de sus movimientos (RF-48).
"""

from datetime import date
from typing import Literal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    String,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

TipoTarjeta = Literal["credito", "debito"]
Franquicia = Literal["visa", "mastercard", "amex", "diners", "otra"]
TipoMovimiento = Literal["recarga", "compra", "reembolso"]


class Tarjeta(TimestampMixin, Base):
    """Tarjeta de crédito o débito simulada del cliente (HU-28, HU-29, RF-46).

    `vencimiento` guarda el primer día del mes de `MM/AA`: la tarjeta sirve hasta el último
    día de ese mes, en hora de Colombia. `eliminada` es un borrado lógico para que las
    recargas históricas conserven su referencia (HU-29).
    """

    __tablename__ = "tarjetas"
    __table_args__ = (
        CheckConstraint("ultimos_4 ~ '^[0-9]{4}$'", name="ultimos_cuatro_digitos"),
        Index("ix_tarjetas_cliente_eliminada", "cliente_id", "eliminada"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[TipoTarjeta] = mapped_column(
        Enum(
            "credito",
            "debito",
            name="tipo_tarjeta",
            native_enum=False,
            length=7,
            create_constraint=True,
        )
    )
    franquicia: Mapped[Franquicia] = mapped_column(
        Enum(
            "visa",
            "mastercard",
            "amex",
            "diners",
            "otra",
            name="franquicia_tarjeta",
            native_enum=False,
            length=10,
            create_constraint=True,
        )
    )
    titular: Mapped[str] = mapped_column(String(100))
    # RNF-12: el número completo y el CVV nunca llegan a la base ni a los logs.
    ultimos_4: Mapped[str] = mapped_column(String(4))
    token: Mapped[str] = mapped_column(String(64))
    vencimiento: Mapped[date] = mapped_column(Date)
    eliminada: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class Movimiento(TimestampMixin, Base):
    """Cambio del saldo del cliente (HU-25, HU-30, HU-31, RF-48).

    `valor` lleva signo y `saldo_resultante` nunca es negativo (RF-48). Los movimientos no se
    editan ni se borran (RNF-16); el saldo del cliente es su suma.
    """

    __tablename__ = "movimientos"
    __table_args__ = (
        # RF-48: ningún movimiento puede dejar el saldo en negativo.
        CheckConstraint("saldo_resultante >= 0", name="saldo_resultante_no_negativo"),
        # El signo depende del tipo: compras negativas, recargas y reembolsos positivos.
        CheckConstraint(
            "(tipo = 'compra' AND valor < 0) OR (tipo IN ('recarga', 'reembolso') AND valor > 0)",
            name="valor_con_el_signo_de_su_tipo",
        ),
        Index("ix_movimientos_cliente_creado_en", "cliente_id", "creado_en"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[TipoMovimiento] = mapped_column(
        Enum(
            "recarga",
            "compra",
            "reembolso",
            name="tipo_movimiento",
            native_enum=False,
            length=9,
            create_constraint=True,
        )
    )
    # BigInteger: una recarga puede acercarse al billón de pesos (SUP-21) y el saldo es su suma.
    valor: Mapped[int] = mapped_column(BigInteger)
    saldo_resultante: Mapped[int] = mapped_column(BigInteger)
    referencia: Mapped[str] = mapped_column(String(20))
