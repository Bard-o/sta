"""Interfaz pública del módulo vuelos. Otros módulos solo llaman a estas funciones.

Concentra la lógica que comparten programar, editar y las series: catálogo de ciudades,
rutas permitidas, conversión de la hora local del origen a UTC, llegada, tipo y capacidad
(RF-12 a RF-16). Ninguna función hace commit: van en la transacción de quien llama.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos
from app.modules.vuelos.models import Ciudad, TipoVuelo, Vuelo
from app.modules.vuelos.schemas import VueloEntrada

# RF-13: nacional 25 + 125; internacional 50 + 200.
_CAPACIDADES: dict[TipoVuelo, tuple[int, int]] = {
    "nacional": (25, 125),
    "internacional": (50, 200),
}
_MENSAJE_RUTA = "Las rutas internacionales salen de Pereira, Bogotá, Medellín, Cali o Cartagena."
_MENSAJE_DUPLICADO = "Ya existe un vuelo de esta ruta a esa hora."


class RutaNoPermitida(DatosInvalidos):
    """RF-14: ruta internacional desde una ciudad no habilitada o entre dos destinos."""

    codigo = "ruta_no_permitida"
    mensaje = "Esta ruta no está permitida."


class VueloDuplicado(Conflicto):
    """RF-16: ya hay un vuelo programado con la misma ruta y salida."""

    codigo = "vuelo_duplicado"
    mensaje = _MENSAJE_DUPLICADO


@dataclass(frozen=True)
class VueloCalculado:
    """Resultado de validar un vuelo, antes de guardarlo."""

    tipo: TipoVuelo
    origen: Ciudad
    destino: Ciudad
    salida: datetime
    llegada: datetime
    duracion_minutos: int
    capacidad_primera: int
    capacidad_economica: int

    @property
    def capacidad_total(self) -> int:
        return self.capacidad_primera + self.capacidad_economica


def listar_ciudades(db: Session) -> list[Ciudad]:
    """Catálogo completo de RF-12, ordenado por nombre."""
    return list(db.scalars(select(Ciudad).order_by(Ciudad.nombre)))


def obtener_ciudad(db: Session, codigo: str) -> Ciudad | None:
    return db.get(Ciudad, codigo)


def capacidad_de(tipo: TipoVuelo) -> tuple[int, int]:
    """Capacidad (primera, económica) según el tipo de vuelo."""
    return _CAPACIDADES[tipo]


def validar_ruta(origen: Ciudad, destino: Ciudad) -> TipoVuelo:
    """Valida RF-14 y devuelve el tipo de vuelo."""
    if origen.codigo == destino.codigo:
        raise DatosInvalidos(campos={"destino": "El destino debe ser distinto del origen."})

    if origen.tipo == "nacional" and destino.tipo == "nacional":
        return "nacional"

    if origen.tipo == "internacional" and destino.tipo == "internacional":
        raise RutaNoPermitida(campos={"destino": _MENSAJE_RUTA})

    nacional = origen if origen.tipo == "nacional" else destino
    if nacional.habilitada_internacional:
        return "internacional"

    raise RutaNoPermitida(campos={"destino": _MENSAJE_RUTA})


def salida_en_utc(fecha: date, hora: time, zona_horaria: str) -> datetime:
    """Convierte la fecha y hora locales del origen a UTC con la zona IANA (RF-15)."""
    return datetime.combine(fecha, hora, tzinfo=ZoneInfo(zona_horaria)).astimezone(UTC)


def validar_vuelo(
    db: Session,
    datos: VueloEntrada,
    *,
    excepto_id: int | None = None,
    ahora: datetime | None = None,
) -> VueloCalculado:
    """Aplica las validaciones de HU-13 y calcula el vuelo sin guardarlo.

    `excepto_id` permite validar una edición sin que el propio vuelo cuente como duplicado.
    `ahora` se inyecta en los tests para comprobar fechas históricas.
    """
    origen = obtener_ciudad(db, datos.origen)
    destino = obtener_ciudad(db, datos.destino)
    campos: dict[str, str] = {}
    if origen is None:
        campos["origen"] = "No es una ciudad del catálogo."
    if destino is None:
        campos["destino"] = "No es una ciudad del catálogo."
    if campos:
        raise DatosInvalidos(campos=campos)

    tipo = validar_ruta(origen, destino)
    salida = salida_en_utc(datos.fecha_salida, datos.hora_salida, origen.zona_horaria)
    if salida <= (ahora or datetime.now(UTC)):
        raise DatosInvalidos(campos={"fecha_salida": "La salida debe ser en el futuro."})

    if _existe_vuelo(db, origen.codigo, destino.codigo, salida, excepto_id):
        raise VueloDuplicado(campos={"hora_salida": _MENSAJE_DUPLICADO})

    capacidad_primera, capacidad_economica = capacidad_de(tipo)
    return VueloCalculado(
        tipo=tipo,
        origen=origen,
        destino=destino,
        salida=salida,
        llegada=salida + timedelta(minutes=datos.duracion_minutos),
        duracion_minutos=datos.duracion_minutos,
        capacidad_primera=capacidad_primera,
        capacidad_economica=capacidad_economica,
    )


def previsualizar_vuelo(
    db: Session, datos: VueloEntrada, *, ahora: datetime | None = None
) -> VueloCalculado:
    """Vista previa de HU-13: mismas validaciones que guardar, sin persistir."""
    return validar_vuelo(db, datos, ahora=ahora)


def _existe_vuelo(
    db: Session,
    origen: str,
    destino: str,
    salida: datetime,
    excepto_id: int | None,
) -> bool:
    consulta = select(Vuelo.id).where(
        Vuelo.estado == "programado",
        Vuelo.origen_codigo == origen,
        Vuelo.destino_codigo == destino,
        Vuelo.salida == salida,
    )
    if excepto_id is not None:
        consulta = consulta.where(Vuelo.id != excepto_id)
    return db.scalar(consulta.limit(1)) is not None
