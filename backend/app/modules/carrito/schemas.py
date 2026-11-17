"""Contrato del carrito (docs/api/iteracion-2.md, HU-22 y HU-23).

El carrito persiste entre sesiones y no bloquea sillas (SUP-15). Cada lectura recalcula el
precio vigente, la disponibilidad, el límite de 5 tiquetes y el plazo de venta de cada tramo.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Clase = Literal["economica", "primera"]
TipoVuelo = Literal["nacional", "internacional"]
EstadoVuelo = Literal["programado", "realizado", "cancelado"]
CodigoAviso = Literal[
    "precio_cambio", "clase_agotada", "limite_tiquetes", "vuelo_no_disponible", "fuera_de_plazo"
]

# Tope técnico. El de negocio (5 tiquetes activos por vuelo, RF-32) es configurable (RNF-23) y lo
# valida el service con `limite_tiquetes`.
MAX_VIAJEROS_SELECCION = 20


# ---------- Entrada ----------


class TramoSeleccionEntrada(BaseModel):
    vuelo_id: int = Field(ge=1)
    clase: Clase


class SeleccionEntrada(BaseModel):
    """HU-22. Un tramo (trayecto único) o dos (ida y regreso, RF-40)."""

    tramos: list[TramoSeleccionEntrada] = Field(
        min_length=1, max_length=2, description="En orden: ida y, si hay, regreso."
    )
    viajeros: int = Field(ge=1, le=MAX_VIAJEROS_SELECCION, description="Cantidad de viajeros.")


class SeleccionCambio(BaseModel):
    """HU-23. Solo cambia lo que se envía; vuelve a validar cupo y límite."""

    viajeros: Annotated[int, Field(ge=1, le=MAX_VIAJEROS_SELECCION)] | None = None
    clases: Annotated[list[Clase], Field(min_length=1, max_length=2)] | None = Field(
        default=None, description="Una por tramo, en el orden de la selección."
    )


# ---------- Salida ----------


class CiudadCarrito(BaseModel):
    codigo: str
    nombre: str
    zona_horaria: str


class VueloCarrito(BaseModel):
    id: int
    codigo: str
    tipo: TipoVuelo
    origen: CiudadCarrito
    destino: CiudadCarrito
    salida: datetime = Field(description="UTC.")
    llegada: datetime = Field(description="UTC.")
    duracion_minutos: int
    estado: EstadoVuelo


class TramoCarrito(BaseModel):
    vuelo: VueloCarrito
    clase: Clase
    precio_unitario: int = Field(description="Precio vigente hoy por viajero (RF-24).")
    precio_al_agregar: int = Field(
        description="Precio por viajero al agregar o modificar la selección."
    )
    promocion_porcentaje: int | None = Field(description="Descuento vigente en la clase.")
    disponibles: int = Field(description="Sillas libres hoy en la clase.")
    tiquetes_activos: int = Field(description="Tiquetes activos del cliente en el vuelo (RF-32).")


class AvisoSeleccion(BaseModel):
    codigo: CodigoAviso
    mensaje: str
    tramo: int = Field(description="0 ida, 1 regreso.")


class SeleccionCarrito(BaseModel):
    id: int
    tramos: list[TramoCarrito]
    viajeros: int
    subtotal: int = Field(description="Suma de precio_unitario × viajeros de los tramos (RF-40).")
    confirmable: bool = Field(
        description="Sin avisos que impidan reservar o comprar (todos menos precio_cambio)."
    )
    avisos: list[AvisoSeleccion]
    reserva_venceria_en: datetime | None = Field(
        description="Si se reservara ahora: 24 h o el límite de venta más próximo (SUP-07). "
        "null si no es confirmable."
    )
    agregada_en: datetime


class Carrito(BaseModel):
    """El carrito del cliente (HU-23, RF-30)."""

    selecciones: list[SeleccionCarrito] = Field(description="La más reciente primero.")
    cantidad: int = Field(description="Selecciones en el carrito, para el contador del menú.")
    total: int = Field(description="Suma de los subtotales de las selecciones confirmables.")
