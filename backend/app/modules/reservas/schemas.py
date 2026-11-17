"""Contrato de reservas, compras y Mis viajes (docs/api/iteracion-2.md, HU-24 a HU-27).

Una reserva y una compra tienen la misma forma (`Viaje`): uno o dos tramos (ida y regreso,
RF-40) y sus viajeros, cada uno con un tiquete por tramo. La clase va por viajero y por tramo
(RF-33). Los patrones de los datos personales son los de usuarios/schemas.py y
frontend/src/lib/persona.ts (RF-03, RF-31).
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from pydantic_core import PydanticCustomError

TipoDocumento = Literal["CC", "TI", "RC", "CE", "PA"]
Genero = Literal["femenino", "masculino", "otro"]
Clase = Literal["economica", "primera"]
TipoVuelo = Literal["nacional", "internacional"]
EstadoVuelo = Literal["programado", "realizado", "cancelado"]
TipoViaje = Literal["reserva", "compra"]
# Los estados de reservas.models (#138). Reserva: vigente, pagada, vencida, cancelada. Compra:
# pendiente (sillas bloqueadas, sin pagar), vencida (el bloqueo pasó), cancelada (se soltó) y
# activa (pagada). La iteración 3 usa realizada, reembolsada y reubicada.
EstadoViaje = Literal[
    "pendiente",
    "vigente",
    "pagada",
    "vencida",
    "activa",
    "cancelada",
    "realizada",
    "reembolsada",
    "reubicada",
]
EstadoTiquete = Literal[
    "bloqueado", "reservado", "comprado", "cancelado", "vencido", "reembolsado", "reubicado"
]

PATRON_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PATRON_DOCUMENTO = r"^[A-Za-z0-9]{3,20}$"
PATRON_TELEFONO = r"^[0-9 +()-]{7,20}$"
PATRON_NOMBRE_PROPIO = r"^\p{L}[\p{L} '.-]*$"

# Tope técnico de viajeros por solicitud. El de negocio (5 tiquetes activos por vuelo, RF-32) es
# configurable (RNF-23) y lo valida el service con `limite_tiquetes`.
MAX_VIAJEROS_SOLICITUD = 20

NombrePropio = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=100, pattern=PATRON_NOMBRE_PROPIO
    ),
]


def _con_siete_digitos(telefono: str) -> str:
    # Mismo tipo de error que el patrón, como en usuarios: «El formato no es válido.»
    if sum(caracter.isdigit() for caracter in telefono) < 7:
        raise PydanticCustomError("string_pattern_mismatch", "Debe tener al menos 7 dígitos.")
    return telefono


Telefono = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=PATRON_TELEFONO),
    AfterValidator(_con_siete_digitos),
]


# ---------- Entrada (HU-24 a HU-27) ----------


class TramoViajeEntrada(BaseModel):
    vuelo_id: int = Field(ge=1)


class ViajeroEntrada(BaseModel):
    """RF-31. Todos los datos son obligatorios: así cada viajero recibe el código de reserva."""

    tipo_documento: TipoDocumento
    numero_documento: str = Field(pattern=PATRON_DOCUMENTO)
    nombres: NombrePropio
    apellidos: NombrePropio
    fecha_nacimiento: date = Field(
        description="La edad se calcula a la fecha de salida de cada tramo (RF-35)."
    )
    genero: Genero
    telefono: Telefono
    email: str = Field(max_length=254, pattern=PATRON_EMAIL)
    contacto_nombre: NombrePropio = Field(description="Contacto de emergencia.")
    contacto_telefono: Telefono
    clases: list[Clase] = Field(
        min_length=1, max_length=2, description="Una por tramo, en el orden de `tramos` (RF-33)."
    )


class ViajeEntrada(BaseModel):
    """Cuerpo de POST /reservas y POST /compras (HU-24, HU-25, HU-26)."""

    tramos: list[TramoViajeEntrada] = Field(
        min_length=1,
        max_length=2,
        description="Ida y, en un trayecto completo, regreso (RF-40).",
    )
    viajeros: list[ViajeroEntrada] = Field(min_length=1, max_length=MAX_VIAJEROS_SOLICITUD)


class PagoReservaEntrada(BaseModel):
    """HU-27. Sin `viajero_ids` (o con null) se pagan todos los viajeros que siguen reservados."""

    viajero_ids: (
        Annotated[list[int], Field(min_length=1, max_length=MAX_VIAJEROS_SOLICITUD)] | None
    ) = None


# ---------- Salida ----------


class CiudadViaje(BaseModel):
    codigo: str
    nombre: str
    zona_horaria: str


class VueloViaje(BaseModel):
    id: int
    codigo: str
    tipo: TipoVuelo
    origen: CiudadViaje
    destino: CiudadViaje
    salida: datetime = Field(description="UTC.")
    llegada: datetime = Field(description="UTC.")
    duracion_minutos: int
    estado: EstadoVuelo


class TramoViaje(BaseModel):
    vuelo: VueloViaje


class TiqueteViaje(BaseModel):
    id: int
    tramo: int = Field(description="Índice en `tramos`: 0 ida, 1 regreso.")
    clase: Clase
    silla: str = Field(description="Fila y letra, p. ej. 18C (SUP-26).")
    numero_silla: int
    precio: int = Field(description="Precio congelado al reservar o al iniciar la compra (RF-24).")
    estado: EstadoTiquete


class ViajeroViaje(BaseModel):
    id: int
    tipo_documento: TipoDocumento
    numero_documento: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    genero: Genero
    telefono: str
    email: str
    contacto_nombre: str
    contacto_telefono: str
    tiquetes: list[TiqueteViaje] = Field(description="Uno por tramo.")


class Viaje(BaseModel):
    """Una reserva o una compra (HU-24 a HU-27)."""

    id: int
    tipo: TipoViaje
    codigo: str = Field(description="Código de reserva de 6 caracteres; pagar lo conserva (HU-27).")
    estado: EstadoViaje
    reserva_id: int | None = Field(
        description="Compra que viene de pagar una reserva: esa reserva."
    )
    compra_id: int | None = Field(
        description="Reserva pagada, toda o en parte: la compra con sus viajeros pagados."
    )
    creada_en: datetime
    vence_en: datetime | None = Field(
        description="Reserva: su vencimiento. Compra pendiente, vencida o soltada: fin del bloqueo "
        "de 15 minutos. Compra pagada: null."
    )
    pagada_en: datetime | None = Field(description="Último pago de una compra.")
    total: int = Field(description="Suma de los precios congelados de todos los tiquetes.")
    total_pendiente: int = Field(
        description="Lo que falta pagar: tiquetes reservados o bloqueados."
    )
    tramos: list[TramoViaje]
    viajeros: list[ViajeroViaje]


class PaginaViajes(BaseModel):
    items: list[Viaje]
    total: int
    pagina: int
    por_pagina: int


class PagoReservaSalida(BaseModel):
    """HU-27: la reserva con sus viajeros pendientes y la compra con los pagados."""

    reserva: Viaje
    compra: Viaje
