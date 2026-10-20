"""Interfaz pública del módulo reservas. Otros módulos solo llaman a estas funciones.

Iteración 1: todavía no existen reservas ni compras, así que estas funciones responden
«sin ventas». Su comportamiento real llega con las HU de la iteración 2 (HU-22 a HU-27) y no
cambia su firma.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class OcupacionVuelo:
    vendidas_primera: int = 0
    vendidas_economica: int = 0
    reservadas_primera: int = 0
    reservadas_economica: int = 0
    # Reservas (no sillas) vigentes: las que se anularían al cancelar el vuelo (HU-16).
    reservas_activas: int = 0

    @property
    def tiquetes_vendidos(self) -> int:
        return self.vendidas_primera + self.vendidas_economica


@dataclass(frozen=True)
class PasajeroVuelo:
    nombres: str
    apellidos: str
    clase: Literal["economica", "primera"]
    numero_silla: int


@dataclass(frozen=True)
class TiqueteActivo:
    tipo: Literal["compra", "reserva"]
    codigo_reserva: str | None
    vuelo_id: int
    vuelo_codigo: str
    origen: str
    destino: str
    salida: datetime


def ocupacion_de_vuelos(db: Session, vuelo_ids: Sequence[int]) -> dict[int, OcupacionVuelo]:
    """Ventas y reservas vigentes por vuelo, en una sola consulta (HU-15, HU-16, HU-18).

    Devuelve una entrada por cada id pedido, aunque no tenga ventas.
    """
    return {vuelo_id: OcupacionVuelo() for vuelo_id in vuelo_ids}


def anular_reservas_de_vuelo(db: Session, vuelo_id: int) -> int:
    """Anula las reservas vigentes del vuelo, libera sus sillas y encola el correo a cada
    cliente (HU-16). Devuelve cuántas anuló. No hace commit."""
    return 0


def pasajeros_de_vuelo(db: Session, vuelo_id: int) -> list[PasajeroVuelo]:
    """Viajeros con tiquete comprado en el vuelo, con su clase y silla (HU-18)."""
    return []


def tiquetes_activos_futuros_de_cliente(db: Session, usuario_id: int) -> list[TiqueteActivo]:
    """Compras y reservas activas del cliente en vuelos que no han salido (HU-09)."""
    return []
