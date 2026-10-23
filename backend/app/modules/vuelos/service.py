"""Interfaz pública del módulo vuelos. Otros módulos solo llaman a estas funciones.

Concentra la lógica que comparten programar, editar y las series: catálogo de ciudades,
rutas permitidas, conversión de la hora local del origen a UTC, llegada, tipo y capacidad
(RF-12 a RF-16). Ninguna función hace commit: van en la transacción de quien llama.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos
from app.modules.auditoria import service as auditoria_service
from app.modules.noticias import service as noticias_service
from app.modules.reservas import service as reservas_service
from app.modules.vuelos.models import Ciudad, TipoVuelo, Vuelo
from app.modules.vuelos.schemas import SerieVuelosEntrada, VueloEntrada

# RF-13: nacional 25 + 125; internacional 50 + 200.
_CAPACIDADES: dict[TipoVuelo, tuple[int, int]] = {
    "nacional": (25, 125),
    "internacional": (50, 200),
}
_MENSAJE_RUTA = "Las rutas internacionales salen de Pereira, Bogotá, Medellín, Cali o Cartagena."
_MENSAJE_DUPLICADO = "Ya existe un vuelo de esta ruta a esa hora."

# SUP-37: el horizonte de las series se mide en la fecha local de Colombia, no en UTC.
_ZONA_NEGOCIO = ZoneInfo("America/Bogota")
_DIAS_SEMANA: dict[str, int] = {
    "lun": 0,
    "mar": 1,
    "mie": 2,
    "jue": 3,
    "vie": 4,
    "sab": 5,
    "dom": 6,
}
# Textos del resumen de la serie (docs/api/iteracion-1.md, HU-14).
_MOTIVO_PASADO = "La salida ya pasó."
_MOTIVO_DUPLICADO = "Ya existe un vuelo igual."


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


@dataclass(frozen=True)
class VueloProgramado:
    """Vuelo guardado, con las ciudades y la ocupación para armar la vista del administrador."""

    vuelo: Vuelo
    origen: Ciudad
    destino: Ciudad
    ocupacion: reservas_service.OcupacionVuelo


@dataclass(frozen=True)
class OcurrenciaOmitida:
    """Fecha de una serie que no se convirtió en vuelo y el motivo (HU-14)."""

    fecha: date
    codigo: Literal["vuelo_duplicado", "salida_en_pasado"]
    motivo: str


@dataclass(frozen=True)
class SerieCalculada:
    """Resultado de validar una serie, antes de guardarla."""

    tipo: TipoVuelo
    origen: Ciudad
    destino: Ciudad
    fechas: list[date]
    omitidas: list[OcurrenciaOmitida]


@dataclass(frozen=True)
class SerieProgramada:
    """Serie guardada: cada ocurrencia es un vuelo independiente (HU-14)."""

    creados: list[Vuelo]
    omitidas: list[OcurrenciaOmitida]
    origen: Ciudad
    destino: Ciudad


def listar_ciudades(db: Session) -> list[Ciudad]:
    """Catálogo completo de RF-12, ordenado por nombre."""
    return list(db.scalars(select(Ciudad).order_by(Ciudad.nombre)))


def obtener_ciudad(db: Session, codigo: str) -> Ciudad | None:
    return db.get(Ciudad, codigo)


def _obtener_ciudades(db: Session, origen: str, destino: str) -> tuple[Ciudad, Ciudad]:
    """Valida que origen y destino estén en el catálogo (RF-12)."""
    ciudad_origen = obtener_ciudad(db, origen)
    ciudad_destino = obtener_ciudad(db, destino)
    if ciudad_origen is None or ciudad_destino is None:
        campos: dict[str, str] = {}
        if ciudad_origen is None:
            campos["origen"] = "No es una ciudad del catálogo."
        if ciudad_destino is None:
            campos["destino"] = "No es una ciudad del catálogo."
        raise DatosInvalidos(campos=campos)
    return ciudad_origen, ciudad_destino


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
    origen, destino = _obtener_ciudades(db, datos.origen, datos.destino)
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


def programar_vuelo(
    db: Session,
    datos: VueloEntrada,
    *,
    usuario_id: int,
    ahora: datetime | None = None,
) -> VueloProgramado:
    """Guarda un vuelo y, en la misma transacción, publica su noticia y lo audita (HU-13).

    No hace commit: el commit y el rollback son de quien llama. El código `STA-nnnnn` lo pone
    la secuencia de la base de datos y no se reutiliza (SUP-01).
    """
    calculado = validar_vuelo(db, datos, ahora=ahora)
    vuelo = _crear_vuelo(
        db,
        calculado,
        precio_economica=datos.precio_economica,
        precio_primera=datos.precio_primera,
        usuario_id=usuario_id,
    )
    return VueloProgramado(
        vuelo=vuelo,
        origen=calculado.origen,
        destino=calculado.destino,
        ocupacion=reservas_service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id],
    )


def previsualizar_serie(
    db: Session, datos: SerieVuelosEntrada, *, ahora: datetime | None = None
) -> SerieCalculada:
    """Vista previa de HU-14: fechas que se crearían y las que se omitirían, sin persistir."""
    return _calcular_serie(db, datos, ahora=ahora)


def programar_serie(
    db: Session,
    datos: SerieVuelosEntrada,
    *,
    usuario_id: int,
    ahora: datetime | None = None,
) -> SerieProgramada:
    """Crea un vuelo independiente por cada fecha de la serie (HU-14, RF-17).

    Las fechas con la salida ya pasada o con un vuelo programado idéntico se omiten y se
    informan; no son un error. No hace commit: el commit y el rollback son de quien llama.
    """
    serie = _calcular_serie(db, datos, ahora=ahora)
    capacidad_primera, capacidad_economica = capacidad_de(serie.tipo)
    creados: list[Vuelo] = []
    for fecha in serie.fechas:
        salida = salida_en_utc(fecha, datos.hora_salida, serie.origen.zona_horaria)
        calculado = VueloCalculado(
            tipo=serie.tipo,
            origen=serie.origen,
            destino=serie.destino,
            salida=salida,
            llegada=salida + timedelta(minutes=datos.duracion_minutos),
            duracion_minutos=datos.duracion_minutos,
            capacidad_primera=capacidad_primera,
            capacidad_economica=capacidad_economica,
        )
        creados.append(
            _crear_vuelo(
                db,
                calculado,
                precio_economica=datos.precio_economica,
                precio_primera=datos.precio_primera,
                usuario_id=usuario_id,
            )
        )
    return SerieProgramada(
        creados=creados,
        omitidas=serie.omitidas,
        origen=serie.origen,
        destino=serie.destino,
    )


def _calcular_serie(
    db: Session, datos: SerieVuelosEntrada, *, ahora: datetime | None
) -> SerieCalculada:
    """Valida la serie y separa las fechas que se crearían de las omitidas (HU-14)."""
    origen, destino = _obtener_ciudades(db, datos.origen, datos.destino)
    tipo = validar_ruta(origen, destino)
    momento = ahora or datetime.now(UTC)
    _validar_periodo(datos, momento)

    # Un día repetido en `dias_semana` no crea dos veces la misma fecha.
    dias = {_DIAS_SEMANA[dia] for dia in datos.dias_semana}
    fechas: list[date] = []
    omitidas: list[OcurrenciaOmitida] = []
    for dia in sorted(dias):
        fecha = datos.desde + timedelta(days=(dia - datos.desde.weekday()) % 7)
        while fecha <= datos.hasta:
            salida = salida_en_utc(fecha, datos.hora_salida, origen.zona_horaria)
            if salida <= momento:
                omitidas.append(
                    OcurrenciaOmitida(fecha=fecha, codigo="salida_en_pasado", motivo=_MOTIVO_PASADO)
                )
            elif _existe_vuelo(db, origen.codigo, destino.codigo, salida, None):
                omitidas.append(
                    OcurrenciaOmitida(
                        fecha=fecha, codigo="vuelo_duplicado", motivo=_MOTIVO_DUPLICADO
                    )
                )
            else:
                fechas.append(fecha)
            fecha += timedelta(days=7)
    fechas.sort()
    omitidas.sort(key=lambda omitida: omitida.fecha)
    return SerieCalculada(
        tipo=tipo,
        origen=origen,
        destino=destino,
        fechas=fechas,
        omitidas=omitidas,
    )


def _validar_periodo(datos: SerieVuelosEntrada, momento: datetime) -> None:
    """SUP-37: periodo con extremos en orden y como máximo 12 meses desde hoy."""
    if datos.hasta < datos.desde:
        raise DatosInvalidos(campos={"hasta": "La fecha final no puede ser anterior a la inicial."})
    if datos.hasta > _limite_de_doce_meses(momento):
        raise DatosInvalidos(campos={"hasta": "Máximo 12 meses desde hoy."})


def _limite_de_doce_meses(momento: datetime) -> date:
    """El mismo día del año siguiente, en la fecha local de Colombia (SUP-37)."""
    hoy = momento.astimezone(_ZONA_NEGOCIO).date()
    try:
        return hoy.replace(year=hoy.year + 1)
    except ValueError:
        # El 29 de febrero no existe en el año siguiente.
        return hoy.replace(year=hoy.year + 1, day=28)


def _crear_vuelo(
    db: Session,
    calculado: VueloCalculado,
    *,
    precio_economica: int,
    precio_primera: int,
    usuario_id: int,
) -> Vuelo:
    """Inserta el vuelo y, en la misma transacción, publica su noticia y lo audita (HU-13/14)."""
    vuelo = Vuelo(
        tipo=calculado.tipo,
        origen_codigo=calculado.origen.codigo,
        destino_codigo=calculado.destino.codigo,
        salida=calculado.salida,
        llegada=calculado.llegada,
        duracion_minutos=calculado.duracion_minutos,
        precio_economica=precio_economica,
        precio_primera=precio_primera,
        capacidad_primera=calculado.capacidad_primera,
        capacidad_economica=calculado.capacidad_economica,
        estado="programado",
    )
    db.add(vuelo)
    # El código sale de la secuencia al insertar y la noticia lo copia (SUP-01, RF-22).
    db.flush()
    db.refresh(vuelo)

    noticias_service.publicar_noticia_vuelo(
        db,
        noticias_service.VueloPublicado(
            vuelo_id=vuelo.id,
            codigo=vuelo.codigo,
            origen=_ciudad_publicada(calculado.origen),
            destino=_ciudad_publicada(calculado.destino),
            salida=vuelo.salida,
            precio_economica=vuelo.precio_economica,
            precio_primera=vuelo.precio_primera,
            # RF-22: la noticia y el carrusel muestran una imagen de la ciudad destino.
            imagen_url=calculado.destino.imagen_url,
        ),
    )
    auditoria_service.registrar(
        db,
        usuario_id=usuario_id,
        accion="vuelo.crear",
        entidad="vuelo",
        entidad_id=vuelo.id,
        despues=_detalle_auditoria(vuelo),
    )
    return vuelo


def _ciudad_publicada(ciudad: Ciudad) -> noticias_service.CiudadPublicada:
    return noticias_service.CiudadPublicada(
        codigo=ciudad.codigo,
        nombre=ciudad.nombre,
        zona_horaria=ciudad.zona_horaria,
    )


def _detalle_auditoria(vuelo: Vuelo) -> dict[str, object]:
    """Copia del vuelo para la auditoría. Las fechas van en ISO 8601: `despues` se guarda en
    JSON y la auditoría rechaza valores que no se puedan serializar (RF-26)."""
    return {
        "codigo": vuelo.codigo,
        "tipo": vuelo.tipo,
        "origen": vuelo.origen_codigo,
        "destino": vuelo.destino_codigo,
        "salida": vuelo.salida.isoformat(),
        "llegada": vuelo.llegada.isoformat(),
        "duracion_minutos": vuelo.duracion_minutos,
        "precio_economica": vuelo.precio_economica,
        "precio_primera": vuelo.precio_primera,
        "capacidad_primera": vuelo.capacidad_primera,
        "capacidad_economica": vuelo.capacidad_economica,
        "estado": vuelo.estado,
    }


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
