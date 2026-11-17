"""Contrato de la búsqueda de vuelos (docs/api/iteracion-2.md, HU-20 y HU-21).

Los vuelos salen de vuelos.service.buscar_vuelos y regresos_de; este módulo valida los rangos,
registra la búsqueda del cliente (RF-29) y da forma a la respuesta. Los nombres de los modelos
llevan el sufijo del módulo para no chocar en el OpenAPI con los de vuelos.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Clase = Literal["economica", "primera"]
TipoVuelo = Literal["nacional", "internacional"]
OrdenBusqueda = Literal["precio", "fecha", "duracion"]


class CiudadBusqueda(BaseModel):
    codigo: str
    nombre: str
    zona_horaria: str = Field(description="Zona IANA para mostrar la hora local (RF-15).")


class PromocionBusqueda(BaseModel):
    porcentaje: int
    fin: datetime = Field(description="UTC: hasta cuándo rige el descuento.")


class ClaseBusqueda(BaseModel):
    precio_base: int
    precio_vigente: int = Field(description="Con el descuento de la promoción vigente (RF-24).")
    promocion: PromocionBusqueda | None
    disponibles: int = Field(description="Descuenta sillas vendidas, reservadas y bloqueadas.")
    agotada: bool


class VueloBusqueda(BaseModel):
    """Un resultado de la búsqueda o de los regresos (HU-20, HU-21)."""

    id: int
    codigo: str
    tipo: TipoVuelo
    origen: CiudadBusqueda
    destino: CiudadBusqueda
    salida: datetime = Field(description="UTC.")
    llegada: datetime = Field(description="UTC.")
    duracion_minutos: int
    economica: ClaseBusqueda
    primera: ClaseBusqueda
    agotado: bool = Field(description="Ninguna de las dos clases tiene sillas (SUP-20).")


class PaginaVuelosBusqueda(BaseModel):
    items: list[VueloBusqueda]
    total: int
    pagina: int
    por_pagina: int
