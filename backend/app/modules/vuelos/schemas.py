"""Contrato del módulo vuelos (docs/api/iteracion-1.md, HU-13 a HU-18).

Horas: las salidas y llegadas se devuelven en UTC; la hora local se calcula con `zona_horaria`
de cada ciudad (RF-15). La única excepción es la entrada de un vuelo: el administrador escribe
la fecha y la hora locales del origen, sin desfase, y el backend las convierte con tzdata.
"""

from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Clase = Literal["economica", "primera"]
TipoVuelo = Literal["nacional", "internacional"]
EstadoVuelo = Literal["programado", "realizado", "cancelado"]
EstadoPromocion = Literal["programada", "vigente", "vencida", "agotada", "cancelada"]
DiaSemana = Literal["lun", "mar", "mie", "jue", "vie", "sab", "dom"]

CodigoCiudad = Annotated[str, Field(pattern=r"^[A-Z]{3}$", description="Código de aeropuerto.")]
Precio = Annotated[int, Field(gt=0, description="COP, entero.")]
# RF-13: mayor que 0 y menor que 24 horas.
DuracionMinutos = Annotated[int, Field(ge=1, lt=1440)]


# ---------- Ciudades (RF-12) ----------


class Ciudad(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    pais: str
    zona_horaria: str = Field(description="Zona IANA, p. ej. Europe/Madrid.")
    tipo: Literal["nacional", "internacional"]
    habilitada_internacional: bool = Field(
        description="Ciudad colombiana con rutas internacionales (RF-14). False en el exterior."
    )
    imagen_url: str = Field(description="Imagen del banco por ciudad destino (SUP-30).")


class CiudadResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    zona_horaria: str


# ---------- Vuelos ----------


class VueloEntrada(BaseModel):
    """HU-13 y HU-15. La fecha y la hora son locales del origen."""

    origen: CodigoCiudad
    destino: CodigoCiudad
    fecha_salida: date
    hora_salida: time
    duracion_minutos: DuracionMinutos
    precio_economica: Precio
    precio_primera: Precio


class Capacidad(BaseModel):
    primera: int
    economica: int
    total: int


class PromocionResumen(BaseModel):
    id: int
    porcentaje: int
    clases: list[Clase]
    inicio: datetime
    fin: datetime
    estado: EstadoPromocion


class Vuelo(BaseModel):
    id: int
    codigo: str = Field(description="STA-nnnnn, nunca se reutiliza (SUP-01).")
    tipo: TipoVuelo
    origen: CiudadResumen
    destino: CiudadResumen
    salida: datetime = Field(description="UTC.")
    llegada: datetime = Field(description="UTC: salida + duración (RF-15).")
    duracion_minutos: int
    precio_economica: int = Field(description="Precio base, sin promoción.")
    precio_primera: int
    capacidad: Capacidad
    estado: EstadoVuelo


class OcupacionClase(BaseModel):
    capacidad: int
    vendidas: int = Field(description="Tiquetes comprados activos.")
    reservadas: int = Field(description="Sillas en reservas vigentes.")
    disponibles: int


class Ocupacion(BaseModel):
    primera: OcupacionClase
    economica: OcupacionClase


class VueloAdmin(Vuelo):
    """Vista del administrador (HU-15, HU-16, HU-18)."""

    ocupacion: Ocupacion
    reservas_activas: int = Field(description="Reservas vigentes que se anularían al cancelar.")
    tiquetes_vendidos: int
    editable: bool
    motivo_no_editable: str | None
    cancelable: bool = Field(description="Programado, no ha salido y sin tiquetes vendidos.")
    promociones: list[PromocionResumen] = Field(description="Vigentes y programadas.")


class PaginaVuelosAdmin(BaseModel):
    items: list[VueloAdmin]
    total: int
    pagina: int
    por_pagina: int


class ClaseDetalle(BaseModel):
    precio_base: int
    precio_vigente: int = Field(description="Con el descuento de la promoción vigente (RF-24).")
    promocion: PromocionResumen | None
    disponibles: int
    agotada: bool


class VueloDetalle(Vuelo):
    """Detalle público del vuelo: lo abren las noticias y el carrusel (HU-19)."""

    economica: ClaseDetalle
    primera: ClaseDetalle


class VueloVistaPrevia(BaseModel):
    """Lo que tendría el vuelo al guardarlo, sin guardarlo (wireframe S08)."""

    tipo: TipoVuelo
    origen: CiudadResumen
    destino: CiudadResumen
    salida: datetime
    llegada: datetime
    duracion_minutos: int
    capacidad: Capacidad


# ---------- Vuelos recurrentes (HU-14) ----------


class SerieVuelosEntrada(BaseModel):
    origen: CodigoCiudad
    destino: CodigoCiudad
    hora_salida: time = Field(description="Hora local del origen.")
    duracion_minutos: DuracionMinutos
    precio_economica: Precio
    precio_primera: Precio
    dias_semana: list[DiaSemana] = Field(
        min_length=1, max_length=7, description="Los 7 días equivalen a diario."
    )
    desde: date
    hasta: date = Field(description="Como máximo 12 meses después de hoy (SUP-37).")


class FechaOmitida(BaseModel):
    fecha: date
    codigo: Literal["vuelo_duplicado", "salida_en_pasado"]
    motivo: str


class SerieVuelosSalida(BaseModel):
    creados: list[Vuelo]
    omitidas: list[FechaOmitida]


class SerieVistaPrevia(BaseModel):
    tipo: TipoVuelo
    capacidad: Capacidad
    fechas: list[date] = Field(description="Fechas en las que se crearía un vuelo.")
    omitidas: list[FechaOmitida]


# ---------- Cancelación y pasajeros (HU-16, HU-18) ----------


class CancelacionVueloSalida(BaseModel):
    vuelo: VueloAdmin
    reservas_anuladas: int


class PasajeroVuelo(BaseModel):
    nombres: str
    apellidos: str
    clase: Clase
    silla: str = Field(description="Fila y letra, p. ej. 12C (SUP-26).")
    numero_silla: int


class PasajerosVueloSalida(BaseModel):
    vuelo: Vuelo
    ocupacion: Ocupacion
    pasajeros: list[PasajeroVuelo]


# ---------- Promociones (HU-17) ----------


class PromocionEntrada(BaseModel):
    porcentaje: int = Field(ge=1, le=90, description="SUP-38.")
    clases: list[Clase] = Field(min_length=1, max_length=2)
    inicio: AwareDatetime
    fin: AwareDatetime


class Promocion(PromocionResumen):
    vuelo_id: int
    vuelo_codigo: str
    origen: CiudadResumen
    destino: CiudadResumen
    salida: datetime
    creada_en: datetime


class PaginaPromociones(BaseModel):
    items: list[Promocion]
    total: int
    pagina: int
    por_pagina: int
