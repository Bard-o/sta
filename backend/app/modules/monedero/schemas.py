"""Contrato del monedero (docs/api/iteracion-2.md, HU-28 a HU-31).

Tarjetas simuladas: el número y el CVV solo se validan y nunca se guardan ni se escriben en los
logs (RNF-12). El saldo es la suma de los movimientos y nunca queda negativo (RF-48).
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

TipoTarjeta = Literal["credito", "debito"]
Franquicia = Literal["visa", "mastercard", "amex", "diners", "otra"]
TipoMovimiento = Literal["recarga", "compra", "reembolso"]

PATRON_NOMBRE_PROPIO = r"^\p{L}[\p{L} '.-]*$"
# La recarga no tiene tope de negocio (SUP-21): este límite técnico solo evita desbordes.
MAXIMO_TECNICO_RECARGA = 1_000_000_000_000


class Monedero(BaseModel):
    saldo: int = Field(description="COP. Suma de todos los movimientos; nunca es negativo (RF-48).")


class TarjetaEntrada(BaseModel):
    """HU-28. La franquicia la deduce el backend a partir del número."""

    tipo: TipoTarjeta
    titular: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=100, pattern=PATRON_NOMBRE_PROPIO
        ),
    ]
    numero: str = Field(
        pattern=r"^\d{13,19}$", description="Solo dígitos, sin espacios. Se valida con Luhn."
    )
    vencimiento: str = Field(pattern=r"^(0[1-9]|1[0-2])/\d{2}$", description="MM/AA.")
    cvv: str = Field(pattern=r"^\d{3,4}$", description="Se valida y se descarta (RNF-12).")


class Tarjeta(BaseModel):
    id: int
    tipo: TipoTarjeta
    franquicia: Franquicia
    titular: str
    numero_enmascarado: str = Field(description="**** y los últimos 4 dígitos.")
    vencimiento: str = Field(description="MM/AA.")
    vencida: bool = Field(description="Ya pasó su mes de vencimiento: no sirve para recargar.")
    creada_en: datetime


class RecargaEntrada(BaseModel):
    tarjeta_id: int = Field(ge=1)
    valor: int = Field(
        gt=0, lt=MAXIMO_TECNICO_RECARGA, description="COP, entero mayor que 0 (HU-30)."
    )


class Movimiento(BaseModel):
    id: int
    tipo: TipoMovimiento
    valor: int = Field(description="COP con signo: + recargas y reembolsos, − compras.")
    saldo_resultante: int
    referencia: str = Field(
        description="Código de reserva (compra, reembolso) o **** 1234 (recarga)."
    )
    creado_en: datetime


class PaginaMovimientos(BaseModel):
    items: list[Movimiento]
    total: int
    pagina: int
    por_pagina: int
