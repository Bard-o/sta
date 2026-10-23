"""Interfaz pública del módulo vuelos. Otros módulos solo llaman a estas funciones.

Concentra la lógica que comparten programar, editar y las series: catálogo de ciudades,
rutas permitidas, conversión de la hora local del origen a UTC, llegada, tipo y capacidad
(RF-12 a RF-16); las promociones por clase con su precio vigente (RF-23, RF-24, RF-25); y el
paso automático a realizado con los pasajeros del vuelo (HU-18, RF-21).
Ninguna función hace commit: van en la transacción de quien llama.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos, NoEncontrado
from app.core.planificador import planificador, registrar_tarea
from app.modules.auditoria import service as auditoria_service
from app.modules.noticias import service as noticias_service
from app.modules.reservas import service as reservas_service
from app.modules.vuelos.models import (
    Ciudad,
    Clase,
    EstadoPromocion,
    EstadoVuelo,
    Promocion,
    TipoVuelo,
    Vuelo,
)
from app.modules.vuelos.schemas import PromocionEntrada, SerieVuelosEntrada, VueloEntrada

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
# Motivos que ve el administrador cuando el vuelo no se puede editar (HU-15).
_MOTIVO_CERRADO = "El vuelo ya se realizó o está cancelado."
_MOTIVO_SALIO = "El vuelo ya salió."
_MOTIVO_VENTAS = "El vuelo tiene reservas activas o compras."
# Promociones (HU-17, RF-23): textos del contrato y del mock del frontend.
_MENSAJE_PROMOCION_DUPLICADA = (
    "Este vuelo ya tiene una promoción para esa clase. Las promociones no se acumulan."
)
_MENSAJE_CLASE_OCUPADA = "Ya hay una promoción vigente o programada para esta clase."
# El estado efectivo se deriva de las fechas salvo cuando ya es terminal (RF-23).
_ESTADOS_TERMINALES: tuple[EstadoPromocion, ...] = ("vencida", "agotada", "cancelada")
_NOMBRE_TAREA_VENCER = "vuelos.vencer_promociones"
_NOMBRE_TAREA_REALIZADOS = "vuelos.marcar_realizados"
# Sillas (SUP-25, SUP-26): la base conserva el número interno y la interfaz muestra fila y letra.
_LETRAS_POR_FILA_CINCO = "ABCDE"
_LETRAS_ECONOMICA_INTERNACIONAL = "ABCDEFGHJK"  # sin la I, para no confundirla con el 1


class RutaNoPermitida(DatosInvalidos):
    """RF-14: ruta internacional desde una ciudad no habilitada o entre dos destinos."""

    codigo = "ruta_no_permitida"
    mensaje = "Esta ruta no está permitida."


class VueloDuplicado(Conflicto):
    """RF-16: ya hay un vuelo programado con la misma ruta y salida."""

    codigo = "vuelo_duplicado"
    mensaje = _MENSAJE_DUPLICADO


class VueloConReservas(Conflicto):
    """RF-18: el vuelo tiene reservas vigentes o compras y no se puede editar."""

    codigo = "vuelo_con_reservas"
    mensaje = "El vuelo tiene reservas activas o compras y no se puede editar."


class VueloCerrado(Conflicto):
    """RF-18: el vuelo ya salió, se realizó o está cancelado."""

    codigo = "vuelo_cerrado"
    mensaje = "El vuelo ya salió, se realizó o está cancelado."


class VueloConTiquetes(Conflicto):
    """RF-19: el vuelo tiene tiquetes vendidos y solo se cancela por fuerza mayor (HU-32)."""

    codigo = "vuelo_con_tiquetes"
    mensaje = "El vuelo tiene tiquetes vendidos; requiere cancelación por fuerza mayor."


class PromocionDuplicada(Conflicto):
    """RF-23: el vuelo ya tiene una promoción activa para alguna de las clases pedidas."""

    codigo = "promocion_duplicada"
    mensaje = _MENSAJE_PROMOCION_DUPLICADA


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
class Gestion:
    """Bloqueos del vuelo para la vista del administrador (HU-15, HU-16)."""

    editable: bool
    motivo_no_editable: str | None
    cancelable: bool


@dataclass(frozen=True)
class VueloGestion:
    """Vuelo guardado, con las ciudades, la ocupación y sus bloqueos (HU-15)."""

    vuelo: Vuelo
    origen: Ciudad
    destino: Ciudad
    ocupacion: reservas_service.OcupacionVuelo
    editable: bool
    motivo_no_editable: str | None
    cancelable: bool


@dataclass(frozen=True)
class CancelacionVuelo:
    """Vuelo cancelado y cuántas reservas se anularon (HU-16)."""

    vuelo: VueloGestion
    reservas_anuladas: int


@dataclass(frozen=True)
class PaginaVuelosGestion:
    """Página del listado del administrador (HU-15, HU-16, HU-18)."""

    items: list[VueloGestion]
    total: int
    pagina: int
    por_pagina: int


@dataclass(frozen=True)
class PromocionVigente:
    """Datos de la promoción que aplica hoy a una clase (RF-24)."""

    id: int
    porcentaje: int
    clases: list[Clase]
    inicio: datetime
    fin: datetime
    estado: EstadoPromocion


@dataclass(frozen=True)
class PrecioVigente:
    """Precio base y precio con descuento de una clase (RF-24)."""

    precio_base: int
    precio: int
    promocion: PromocionVigente | None


@dataclass(frozen=True)
class ClaseDetalleVuelo:
    """Precio y disponibilidad de una clase en el detalle público (HU-19)."""

    precio_base: int
    precio: int
    promocion: PromocionVigente | None
    disponibles: int
    agotada: bool


@dataclass(frozen=True)
class VueloDetalleGestion:
    """Detalle público del vuelo: precio vigente y sillas por clase (HU-19)."""

    vuelo: Vuelo
    origen: Ciudad
    destino: Ciudad
    economica: ClaseDetalleVuelo
    primera: ClaseDetalleVuelo


@dataclass(frozen=True)
class PasajeroGestion:
    """Pasajero del vuelo con su clase y su silla (HU-18, SUP-26)."""

    nombres: str
    apellidos: str
    clase: Clase
    numero_silla: int
    silla: str


@dataclass(frozen=True)
class PasajerosVueloGestion:
    """Pasajeros y ocupación por clase de un vuelo (HU-18)."""

    vuelo: Vuelo
    origen: Ciudad
    destino: Ciudad
    ocupacion: reservas_service.OcupacionVuelo
    pasajeros: list[PasajeroGestion]


@dataclass(frozen=True)
class PromocionGestion:
    """Promoción guardada con los datos del vuelo y su estado efectivo (HU-17)."""

    promocion: Promocion
    vuelo: Vuelo
    origen: Ciudad
    destino: Ciudad
    clases: list[Clase]
    estado: EstadoPromocion


@dataclass(frozen=True)
class PaginaPromocionesGestion:
    """Página del listado de promociones (HU-17)."""

    items: list[PromocionGestion]
    total: int
    pagina: int
    por_pagina: int


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
) -> VueloGestion:
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
    ocupacion = reservas_service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    return _armar_gestion(vuelo, calculado.origen, calculado.destino, ocupacion, ahora=ahora)


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


# ---------- Gestión y edición (HU-15) ----------


def listar_vuelos_gestion(
    db: Session,
    *,
    estado: EstadoVuelo = "programado",
    desde: date | None = None,
    hasta: date | None = None,
    q: str | None = None,
    pagina: int = 1,
    por_pagina: int = 20,
    ahora: datetime | None = None,
) -> PaginaVuelosGestion:
    """Vuelos del administrador con filtros, orden y ocupación (HU-15, HU-16, HU-18).

    Los programados van por salida ascendente; los realizados y cancelados, del más reciente
    al más antiguo. `desde` y `hasta` son fechas de Colombia inclusivas y se aplican a la
    salida (programados y cancelados) o a la llegada (realizados). No hace commit.
    """
    filtros = _filtros_listado(db, estado=estado, desde=desde, hasta=hasta, q=q)
    total = db.scalar(select(func.count()).select_from(Vuelo).where(*filtros)) or 0
    orden, desempate = _orden_listado(estado)
    vuelos = list(
        db.scalars(
            select(Vuelo)
            .where(*filtros)
            .order_by(orden, desempate)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
    )
    ciudades = _ciudades_por_codigo(
        db,
        {codigo for vuelo in vuelos for codigo in (vuelo.origen_codigo, vuelo.destino_codigo)},
    )
    # Una sola consulta para la ocupación de toda la página (HU-15).
    ocupaciones = reservas_service.ocupacion_de_vuelos(db, [vuelo.id for vuelo in vuelos])
    items = [
        _armar_gestion(
            vuelo,
            ciudades[vuelo.origen_codigo],
            ciudades[vuelo.destino_codigo],
            ocupaciones.get(vuelo.id, reservas_service.OcupacionVuelo()),
            ahora=ahora,
        )
        for vuelo in vuelos
    ]
    return PaginaVuelosGestion(items=items, total=total, pagina=pagina, por_pagina=por_pagina)


def obtener_vuelo_gestion(
    db: Session, vuelo_id: int, *, ahora: datetime | None = None
) -> VueloGestion:
    """Un vuelo con su ocupación y sus bloqueos, para el formulario de edición (HU-15)."""
    return _gestion_de_vuelo(db, _vuelo_o_no_encontrado(db, vuelo_id), ahora=ahora)


def obtener_vuelo_detalle(
    db: Session, vuelo_id: int, *, ahora: datetime | None = None
) -> VueloDetalleGestion:
    """Detalle público del vuelo con el precio vigente de cada clase (HU-19, RF-24).

    Responde para cualquier `estado`: el frontend avisa si el vuelo ya no está programado.
    Una promoción solo aplica a un vuelo vendible (programado y que no ha salido); en los
    demás casos el precio vuelve a la base y `promocion` es None. No hace commit.
    """
    momento = ahora or datetime.now(UTC)
    vuelo = _vuelo_o_no_encontrado(db, vuelo_id)
    origen, destino = _obtener_ciudades(db, vuelo.origen_codigo, vuelo.destino_codigo)
    ocupacion = reservas_service.ocupacion_de_vuelos(db, [vuelo.id]).get(
        vuelo.id, reservas_service.OcupacionVuelo()
    )

    promociones: dict[Clase, PromocionVigente] = {}
    if vuelo.estado == "programado" and vuelo.salida > momento:
        for promocion in _promociones_activas(db, vuelo.id, ahora=momento):
            if estado_de(promocion, ahora=momento) == "vigente":
                vigente = _promocion_vigente_de(promocion)
                for clase in vigente.clases:
                    promociones[clase] = vigente

    return VueloDetalleGestion(
        vuelo=vuelo,
        origen=origen,
        destino=destino,
        economica=_clase_detalle(
            vuelo.capacidad_economica,
            ocupacion.vendidas_economica,
            ocupacion.reservadas_economica,
            vuelo.precio_economica,
            promociones.get("economica"),
        ),
        primera=_clase_detalle(
            vuelo.capacidad_primera,
            ocupacion.vendidas_primera,
            ocupacion.reservadas_primera,
            vuelo.precio_primera,
            promociones.get("primera"),
        ),
    )


def _clase_detalle(
    capacidad: int,
    vendidas: int,
    reservadas: int,
    precio_base: int,
    promocion: PromocionVigente | None,
) -> ClaseDetalleVuelo:
    """Precio y sillas de una clase; la promoción solo cambia el precio mostrado (RF-24)."""
    disponibles = capacidad - vendidas - reservadas
    return ClaseDetalleVuelo(
        precio_base=precio_base,
        precio=(
            precio_con_descuento(precio_base, promocion.porcentaje)
            if promocion is not None
            else precio_base
        ),
        promocion=promocion,
        disponibles=disponibles,
        agotada=disponibles <= 0,
    )


def editar_vuelo(
    db: Session,
    vuelo_id: int,
    datos: VueloEntrada,
    *,
    usuario_id: int,
    ahora: datetime | None = None,
) -> VueloGestion:
    """Edita un vuelo programado sin ventas ni reservas vigentes (HU-15, RF-18).

    Vuelve a aplicar las validaciones de HU-13 excluyendo al propio vuelo de la unicidad,
    recalcula tipo, capacidad y llegada y conserva el código. En la misma transacción
    actualiza sus noticias y audita solo los campos que cambiaron (RF-26). No hace commit:
    el commit y el rollback son de quien llama.
    """
    momento = ahora or datetime.now(UTC)
    vuelo = _vuelo_o_no_encontrado(db, vuelo_id)
    ocupacion = reservas_service.ocupacion_de_vuelos(db, [vuelo.id]).get(
        vuelo.id, reservas_service.OcupacionVuelo()
    )
    evaluar_edicion(vuelo, ocupacion, ahora=momento)

    calculado = validar_vuelo(db, datos, excepto_id=vuelo.id, ahora=momento)
    antes = _detalle_auditoria(vuelo)
    _actualizar_vuelo(vuelo, calculado, datos)
    despues = _detalle_auditoria(vuelo)
    # RF-26: solo se audita lo que cambió; un PUT idéntico no deja registro.
    if antes != despues:
        noticias_service.actualizar_noticias_de_vuelo(db, _vuelo_publicado(vuelo, calculado))
        auditoria_service.registrar(
            db,
            usuario_id=usuario_id,
            accion="vuelo.editar",
            entidad="vuelo",
            entidad_id=vuelo.id,
            antes=_cambios(antes, despues),
            despues=_cambios(despues, antes),
        )
    return _armar_gestion(vuelo, calculado.origen, calculado.destino, ocupacion, ahora=momento)


def cancelar_vuelo(
    db: Session,
    vuelo_id: int,
    *,
    usuario_id: int,
    ahora: datetime | None = None,
) -> CancelacionVuelo:
    """Cancela un vuelo programado sin tiquetes vendidos (HU-16, RF-19, RF-26).

    En la misma transacción anula las reservas vigentes (que liberan sus sillas y encolan el
    correo a cada cliente), pasa a `cancelada` sus promociones activas, retira las noticias del
    carrusel y audita la cancelación. El código del vuelo no se reutiliza (SUP-01). No hace
    commit: el commit y el rollback son de quien llama.
    """
    momento = ahora or datetime.now(UTC)
    # El lock serializa dos cancelaciones simultáneas y la creación de promociones del vuelo.
    vuelo = _vuelo_bloqueado(db, vuelo_id)
    ocupacion = reservas_service.ocupacion_de_vuelos(db, [vuelo.id]).get(
        vuelo.id, reservas_service.OcupacionVuelo()
    )
    evaluar_cancelacion(vuelo, ocupacion, ahora=momento)

    vuelo.estado = "cancelado"
    reservas_anuladas = reservas_service.anular_reservas_de_vuelo(db, vuelo.id)
    promociones_canceladas = _cancelar_promociones_de_vuelo(db, vuelo.id, ahora=momento)
    noticias_service.retirar_noticias_de_vuelo(db, vuelo.id)
    auditoria_service.registrar(
        db,
        usuario_id=usuario_id,
        accion="vuelo.cancelar",
        entidad="vuelo",
        entidad_id=vuelo.id,
        antes={"estado": "programado"},
        despues={
            "estado": "cancelado",
            "reservas_anuladas": reservas_anuladas,
            "promociones_canceladas": promociones_canceladas,
        },
    )
    origen, destino = _obtener_ciudades(db, vuelo.origen_codigo, vuelo.destino_codigo)
    # Sin tiquetes vendidos y con las reservas anuladas ya no queda ocupación que informar.
    return CancelacionVuelo(
        vuelo=_armar_gestion(
            vuelo, origen, destino, reservas_service.OcupacionVuelo(), ahora=momento
        ),
        reservas_anuladas=reservas_anuladas,
    )


def evaluar_gestion(
    vuelo: Vuelo,
    ocupacion: reservas_service.OcupacionVuelo,
    *,
    ahora: datetime | None = None,
) -> Gestion:
    """Reglas de HU-15 y HU-16: cuándo se edita y cuándo se cancela un vuelo."""
    momento = ahora or datetime.now(UTC)
    cerrado = vuelo.estado != "programado"
    salio = vuelo.salida <= momento
    if cerrado:
        editable, motivo = False, _MOTIVO_CERRADO
    elif salio:
        editable, motivo = False, _MOTIVO_SALIO
    elif _tiene_ventas(ocupacion):
        editable, motivo = False, _MOTIVO_VENTAS
    else:
        editable, motivo = True, None
    # RF-19: las reservas no impiden cancelar; los tiquetes vendidos, sí.
    cancelable = not cerrado and not salio and ocupacion.tiquetes_vendidos == 0
    return Gestion(editable=editable, motivo_no_editable=motivo, cancelable=cancelable)


def evaluar_edicion(
    vuelo: Vuelo,
    ocupacion: reservas_service.OcupacionVuelo,
    *,
    ahora: datetime | None = None,
) -> None:
    """RF-18: rechaza la edición de un vuelo cerrado o con ventas, con el motivo del contrato."""
    momento = ahora or datetime.now(UTC)
    if vuelo.estado != "programado" or vuelo.salida <= momento:
        raise VueloCerrado()
    if _tiene_ventas(ocupacion):
        raise VueloConReservas()


def evaluar_cancelacion(
    vuelo: Vuelo,
    ocupacion: reservas_service.OcupacionVuelo,
    *,
    ahora: datetime | None = None,
) -> None:
    """RF-19: rechaza cancelar un vuelo cerrado o con tiquetes vendidos."""
    momento = ahora or datetime.now(UTC)
    if vuelo.estado != "programado" or vuelo.salida <= momento:
        raise VueloCerrado()
    if ocupacion.tiquetes_vendidos > 0:
        raise VueloConTiquetes()


def _cancelar_promociones_de_vuelo(db: Session, vuelo_id: int, *, ahora: datetime) -> list[int]:
    """Pasa a `cancelada` las promociones activas y cierra su noticia (HU-16, RF-23, RF-25)."""
    canceladas: list[int] = []
    for promocion in _promociones_activas(db, vuelo_id, ahora=ahora):
        promocion.estado = "cancelada"
        noticias_service.terminar_noticia_promocion(db, promocion.id, "cancelada")
        canceladas.append(promocion.id)
    return canceladas


def _tiene_ventas(ocupacion: reservas_service.OcupacionVuelo) -> bool:
    return ocupacion.reservas_activas > 0 or ocupacion.tiquetes_vendidos > 0


def _armar_gestion(
    vuelo: Vuelo,
    origen: Ciudad,
    destino: Ciudad,
    ocupacion: reservas_service.OcupacionVuelo,
    *,
    ahora: datetime | None = None,
) -> VueloGestion:
    gestion = evaluar_gestion(vuelo, ocupacion, ahora=ahora)
    return VueloGestion(
        vuelo=vuelo,
        origen=origen,
        destino=destino,
        ocupacion=ocupacion,
        editable=gestion.editable,
        motivo_no_editable=gestion.motivo_no_editable,
        cancelable=gestion.cancelable,
    )


def _gestion_de_vuelo(db: Session, vuelo: Vuelo, *, ahora: datetime | None = None) -> VueloGestion:
    ocupacion = reservas_service.ocupacion_de_vuelos(db, [vuelo.id]).get(
        vuelo.id, reservas_service.OcupacionVuelo()
    )
    origen, destino = _obtener_ciudades(db, vuelo.origen_codigo, vuelo.destino_codigo)
    return _armar_gestion(vuelo, origen, destino, ocupacion, ahora=ahora)


def _vuelo_o_no_encontrado(db: Session, vuelo_id: int) -> Vuelo:
    vuelo = db.get(Vuelo, vuelo_id)
    if vuelo is None:
        raise NoEncontrado("El vuelo no existe.")
    return vuelo


def _actualizar_vuelo(vuelo: Vuelo, calculado: VueloCalculado, datos: VueloEntrada) -> None:
    """Aplica al vuelo lo calculado; el código y el estado no cambian (HU-15)."""
    vuelo.tipo = calculado.tipo
    vuelo.origen_codigo = calculado.origen.codigo
    vuelo.destino_codigo = calculado.destino.codigo
    vuelo.salida = calculado.salida
    vuelo.llegada = calculado.llegada
    vuelo.duracion_minutos = calculado.duracion_minutos
    vuelo.precio_economica = datos.precio_economica
    vuelo.precio_primera = datos.precio_primera
    vuelo.capacidad_primera = calculado.capacidad_primera
    vuelo.capacidad_economica = calculado.capacidad_economica


def _cambios(nuevo: dict[str, object], anterior: dict[str, object]) -> dict[str, object]:
    """Solo los campos que cambiaron, para `antes` o `despues` de la auditoría (RF-26)."""
    return {clave: valor for clave, valor in nuevo.items() if anterior.get(clave) != valor}


def _vuelo_publicado(vuelo: Vuelo, calculado: VueloCalculado) -> noticias_service.VueloPublicado:
    """Copia del vuelo para la noticia, con la imagen de la ciudad destino (RF-22)."""
    return _publicado_de(vuelo, calculado.origen, calculado.destino)


def _publicado_de(vuelo: Vuelo, origen: Ciudad, destino: Ciudad) -> noticias_service.VueloPublicado:
    """Copia del vuelo para una noticia, con la imagen de la ciudad destino (RF-22, RF-25)."""
    return noticias_service.VueloPublicado(
        vuelo_id=vuelo.id,
        codigo=vuelo.codigo,
        origen=_ciudad_publicada(origen),
        destino=_ciudad_publicada(destino),
        salida=vuelo.salida,
        precio_economica=vuelo.precio_economica,
        precio_primera=vuelo.precio_primera,
        imagen_url=destino.imagen_url,
    )


def _filtros_listado(
    db: Session,
    *,
    estado: EstadoVuelo,
    desde: date | None,
    hasta: date | None,
    q: str | None,
) -> list[object]:
    """Filtros de `GET /vuelos`: estado, fechas de Colombia y texto (HU-15)."""
    columna = Vuelo.llegada if estado == "realizado" else Vuelo.salida
    filtros: list[object] = [Vuelo.estado == estado]
    if desde is not None:
        filtros.append(columna >= _inicio_del_dia(desde))
    if hasta is not None:
        filtros.append(columna < _inicio_del_dia(hasta + timedelta(days=1)))
    texto = (q or "").strip()
    if texto:
        filtros.append(_filtro_texto(db, texto))
    return filtros


def _orden_listado(estado: EstadoVuelo) -> tuple[object, object]:
    """Programados: salida ascendente. Realizados y cancelados: del más reciente al más
    antiguo (los realizados por llegada, como su filtro de fechas)."""
    if estado == "realizado":
        return Vuelo.llegada.desc(), Vuelo.id.desc()
    if estado == "cancelado":
        return Vuelo.salida.desc(), Vuelo.id.desc()
    return Vuelo.salida.asc(), Vuelo.id.asc()


def _inicio_del_dia(fecha: date) -> datetime:
    """Medianoche en Colombia, que es la zona de los filtros de fecha del contrato."""
    return datetime.combine(fecha, time.min, tzinfo=_ZONA_NEGOCIO).astimezone(UTC)


def _filtro_texto(db: Session, texto: str) -> object:
    """Código del vuelo o nombre de la ciudad de origen/destino, sin tildes (HU-15)."""
    buscado = _sin_tildes(texto)
    codigos = [
        ciudad.codigo
        for ciudad in db.scalars(select(Ciudad))
        if buscado in _sin_tildes(ciudad.nombre) or buscado in _sin_tildes(ciudad.codigo)
    ]
    condiciones = [Vuelo.codigo.ilike(f"%{_escapar_like(texto)}%", escape="\\")]
    if codigos:
        condiciones.append(Vuelo.origen_codigo.in_(codigos))
        condiciones.append(Vuelo.destino_codigo.in_(codigos))
    return or_(*condiciones)


def _sin_tildes(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.strip().lower()


def _escapar_like(texto: str) -> str:
    """Los comodines de `LIKE` del texto del administrador son literales."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ciudades_por_codigo(db: Session, codigos: set[str]) -> dict[str, Ciudad]:
    """Las ciudades de la página en una sola consulta, sin N+1."""
    if not codigos:
        return {}
    return {
        ciudad.codigo: ciudad
        for ciudad in db.scalars(select(Ciudad).where(Ciudad.codigo.in_(codigos)))
    }


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

    noticias_service.publicar_noticia_vuelo(db, _vuelo_publicado(vuelo, calculado))
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


# ---------- Vuelos realizados y pasajeros (HU-18, RF-21) ----------


def marcar_realizados(db: Session, ahora: datetime) -> int:
    """Pasa a `realizado` cada vuelo programado cuya llegada ya pasó (HU-18, RF-21, RNF-18).

    La ejecuta el planificador cada minuto; procesa todo lo atrasado, incluido lo que llegó
    mientras el servidor estuvo apagado, y es idempotente. Retira las noticias del vuelo para
    que salga del carrusel. No hace commit: el planificador confirma la transacción.
    """
    vuelos = list(
        db.scalars(select(Vuelo).where(Vuelo.estado == "programado", Vuelo.llegada <= ahora))
    )
    for vuelo in vuelos:
        vuelo.estado = "realizado"
        noticias_service.retirar_noticias_de_vuelo(db, vuelo.id)
    return len(vuelos)


def listar_pasajeros_vuelo(db: Session, vuelo_id: int) -> PasajerosVueloGestion:
    """Pasajeros con su clase y silla y la ocupación por clase (HU-18, RF-21).

    Los pasajeros salen de `reservas.pasajeros_de_vuelo`; hasta la iteración 2 la lista está
    vacía. Responde para cualquier estado del vuelo. No hace commit.
    """
    vuelo = _vuelo_o_no_encontrado(db, vuelo_id)
    origen, destino = _obtener_ciudades(db, vuelo.origen_codigo, vuelo.destino_codigo)
    ocupacion = reservas_service.ocupacion_de_vuelos(db, [vuelo.id]).get(
        vuelo.id, reservas_service.OcupacionVuelo()
    )
    pasajeros = [
        PasajeroGestion(
            nombres=pasajero.nombres,
            apellidos=pasajero.apellidos,
            clase=pasajero.clase,
            numero_silla=pasajero.numero_silla,
            silla=nombre_de_silla(vuelo.tipo, pasajero.clase, pasajero.numero_silla),
        )
        for pasajero in reservas_service.pasajeros_de_vuelo(db, vuelo.id)
    ]
    return PasajerosVueloGestion(
        vuelo=vuelo,
        origen=origen,
        destino=destino,
        ocupacion=ocupacion,
        pasajeros=pasajeros,
    )


def nombre_de_silla(tipo: TipoVuelo, clase: Clase, numero: int) -> str:
    """Fila y letra de una silla a partir de su número interno (Apéndice A, SUP-25, SUP-26).

    Nacional y primera internacional: cinco sillas por fila, letras A–E. Económica
    internacional: diez por fila desde la 11, letras A–K sin la I.
    """
    if tipo == "internacional" and clase == "economica":
        m = numero - 50
        return f"{10 + (m - 1) // 10 + 1}{_LETRAS_ECONOMICA_INTERNACIONAL[(m - 1) % 10]}"
    return f"{(numero - 1) // 5 + 1}{_LETRAS_POR_FILA_CINCO[(numero - 1) % 5]}"


# ---------- Promociones (HU-17, RF-23 a RF-26) ----------


def estado_de(promocion: Promocion, *, ahora: datetime | None = None) -> EstadoPromocion:
    """Estado efectivo de la promoción (RF-23).

    Los estados terminales guardados (`vencida`, `agotada`, `cancelada`) ganan; el resto se
    deriva de `inicio` y `fin` con la hora inyectada. Así un `inicio` pasado queda vigente
    de inmediato y una promoción vence a su hora aunque el planificador no haya corrido.
    """
    if promocion.estado in _ESTADOS_TERMINALES:
        return promocion.estado
    momento = ahora or datetime.now(UTC)
    if momento < promocion.inicio:
        return "programada"
    if momento < promocion.fin:
        return "vigente"
    return "vencida"


def clases_de(promocion: Promocion) -> list[Clase]:
    """Clases a las que aplica la promoción, en el orden del contrato (SUP-05)."""
    return [clase for clase in ("economica", "primera") if _aplica(promocion, clase)]


def precio_con_descuento(precio_base: int, porcentaje: int) -> int:
    """RF-24: el precio con descuento se redondea hacia abajo al peso entero."""
    return precio_base * (100 - porcentaje) // 100


def precio_vigente(
    db: Session, vuelo_id: int, clase: Clase, *, ahora: datetime | None = None
) -> PrecioVigente:
    """Precio base y precio con descuento de una clase (RF-24).

    Es la función que usarán la búsqueda y el detalle público: un tiquete anterior conserva
    el precio que pagó porque el precio base del vuelo nunca se modifica.
    """
    vuelo = _vuelo_o_no_encontrado(db, vuelo_id)
    base = vuelo.precio_economica if clase == "economica" else vuelo.precio_primera
    promocion = _promocion_vigente(db, vuelo_id, clase, ahora=ahora)
    if promocion is None:
        return PrecioVigente(precio_base=base, precio=base, promocion=None)
    return PrecioVigente(
        precio_base=base,
        precio=precio_con_descuento(base, promocion.porcentaje),
        promocion=_promocion_vigente_de(promocion),
    )


def _promocion_vigente_de(promocion: Promocion) -> PromocionVigente:
    """Forma pública de una promoción vigente, con sus clases y su estado (HU-19)."""
    return PromocionVigente(
        id=promocion.id,
        porcentaje=promocion.porcentaje,
        clases=clases_de(promocion),
        inicio=promocion.inicio,
        fin=promocion.fin,
        estado="vigente",
    )


def crear_promocion(
    db: Session,
    vuelo_id: int,
    datos: PromocionEntrada,
    *,
    usuario_id: int,
    ahora: datetime | None = None,
) -> PromocionGestion:
    """Crea una promoción, publica su noticia y la audita (HU-17, RF-23, RF-25, RF-26).

    No hace commit: el commit y el rollback son de quien llama. Bloquea el vuelo para que dos
    creaciones simultáneas no acumulen promociones en la misma clase (RF-23). Si las clases
    ya no tienen sillas disponibles, la promoción nace `agotada`.
    """
    momento = ahora or datetime.now(UTC)
    vuelo = _vuelo_bloqueado(db, vuelo_id)
    _validar_promocion(vuelo, datos, momento)
    # Libera el índice único de las que ya vencieron pero el planificador aún no marcó.
    # El flush es necesario porque la sesión no hace autoflush: el índice parcial todavía
    # vería la promoción vieja como programada al insertar la nueva.
    _vencer_promociones(db, momento, vuelo_id=vuelo.id)
    db.flush()

    clases = _clases_de_entrada(datos.clases)
    if _clases_ocupadas(db, vuelo.id, clases, ahora=momento):
        raise PromocionDuplicada(campos={"clases": _MENSAJE_CLASE_OCUPADA})

    promocion = Promocion(
        vuelo_id=vuelo.id,
        porcentaje=datos.porcentaje,
        aplica_economica="economica" in clases,
        aplica_primera="primera" in clases,
        inicio=datos.inicio.astimezone(UTC),
        fin=datos.fin.astimezone(UTC),
        estado="programada",
        creada_en=momento,
    )
    db.add(promocion)
    db.flush()

    origen, destino = _obtener_ciudades(db, vuelo.origen_codigo, vuelo.destino_codigo)
    noticias_service.publicar_noticia_promocion(
        db, _promocion_publicada(promocion, vuelo, origen, destino)
    )
    auditoria_service.registrar(
        db,
        usuario_id=usuario_id,
        accion="promocion.crear",
        entidad="promocion",
        entidad_id=promocion.id,
        despues=_detalle_auditoria_promocion(promocion),
    )
    # Caso borde: si las clases ya están agotadas, no se ofrece una promoción falsa.
    marcar_promociones_agotadas(db, vuelo.id, ahora=momento)
    return _armar_promocion(promocion, vuelo, origen, destino, ahora=momento)


def listar_promociones(
    db: Session,
    *,
    estado: EstadoPromocion | None = None,
    pagina: int = 1,
    por_pagina: int = 20,
    ahora: datetime | None = None,
) -> PaginaPromocionesGestion:
    """Promociones de todos los vuelos, de la más reciente a la más antigua (HU-17).

    `estado` filtra por el estado efectivo calculado en la propia consulta, así una
    promoción que acaba de vencer no espera al planificador. No hace commit.
    """
    momento = ahora or datetime.now(UTC)
    filtros = []
    if estado is not None:
        filtros.append(_estado_efectivo_sql(momento) == estado)
    total = db.scalar(select(func.count()).select_from(Promocion).where(*filtros)) or 0
    promociones = list(
        db.scalars(
            select(Promocion)
            .where(*filtros)
            .order_by(Promocion.creada_en.desc(), Promocion.id.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
    )
    vuelos = _vuelos_por_id(db, {promocion.vuelo_id for promocion in promociones})
    ciudades = _ciudades_por_codigo(
        db,
        {
            codigo
            for vuelo in vuelos.values()
            for codigo in (vuelo.origen_codigo, vuelo.destino_codigo)
        },
    )
    items = [
        _armar_promocion(
            promocion,
            vuelos[promocion.vuelo_id],
            ciudades[vuelos[promocion.vuelo_id].origen_codigo],
            ciudades[vuelos[promocion.vuelo_id].destino_codigo],
            ahora=momento,
        )
        for promocion in promociones
    ]
    return PaginaPromocionesGestion(items=items, total=total, pagina=pagina, por_pagina=por_pagina)


def marcar_promociones_agotadas(
    db: Session, vuelo_id: int, *, ahora: datetime | None = None
) -> list[int]:
    """Marca agotadas las promociones cuyas clases ya no tienen sillas (RF-23).

    Si la promoción aplica a dos clases, sigue disponible mientras quede al menos una silla
    en cualquiera de ellas. La llama `reservas` al vender la última silla; también la usa la
    creación para el caso en que la clase ya estaba llena. No hace commit.
    """
    momento = ahora or datetime.now(UTC)
    vuelo = _vuelo_o_no_encontrado(db, vuelo_id)
    ocupacion = reservas_service.ocupacion_de_vuelos(db, [vuelo.id]).get(
        vuelo.id, reservas_service.OcupacionVuelo()
    )
    disponibles: dict[Clase, int] = {
        "economica": (
            vuelo.capacidad_economica
            - ocupacion.vendidas_economica
            - ocupacion.reservadas_economica
        ),
        "primera": (
            vuelo.capacidad_primera - ocupacion.vendidas_primera - ocupacion.reservadas_primera
        ),
    }
    agotadas: list[int] = []
    for promocion in _promociones_activas(db, vuelo.id, ahora=momento):
        if all(disponibles[clase] <= 0 for clase in clases_de(promocion)):
            promocion.estado = "agotada"
            noticias_service.terminar_noticia_promocion(db, promocion.id, "agotada")
            agotadas.append(promocion.id)
    return agotadas


def vencer_promociones(db: Session, ahora: datetime) -> int:
    """Pasa a `vencida` toda promoción cuyo fin ya pasó (RF-23, RNF-18).

    La ejecuta el planificador cada minuto; procesa todo lo vencido hasta `ahora` y es
    idempotente. No hace commit: el planificador confirma la transacción.
    """
    return _vencer_promociones(db, ahora)


def _vencer_promociones(db: Session, ahora: datetime, *, vuelo_id: int | None = None) -> int:
    consulta = select(Promocion).where(Promocion.estado == "programada", Promocion.fin <= ahora)
    if vuelo_id is not None:
        consulta = consulta.where(Promocion.vuelo_id == vuelo_id)
    promociones = list(db.scalars(consulta))
    for promocion in promociones:
        promocion.estado = "vencida"
    return len(promociones)


def _validar_promocion(vuelo: Vuelo, datos: PromocionEntrada, momento: datetime) -> None:
    """RF-23: solo vuelos programados que no han salido, con fin futuro y posterior al inicio."""
    if vuelo.estado != "programado" or vuelo.salida <= momento:
        raise VueloCerrado()
    if datos.fin <= datos.inicio:
        raise DatosInvalidos(campos={"fin": "El fin debe ser posterior al inicio."})
    if datos.fin <= momento:
        raise DatosInvalidos(campos={"fin": "El fin debe ser una fecha futura."})


def _vuelo_bloqueado(db: Session, vuelo_id: int) -> Vuelo:
    """Vuelo con lock de fila: serializa las creaciones de promociones del mismo vuelo."""
    vuelo = db.scalar(select(Vuelo).where(Vuelo.id == vuelo_id).with_for_update())
    if vuelo is None:
        raise NoEncontrado("El vuelo no existe.")
    return vuelo


def _promociones_activas(
    db: Session, vuelo_id: int, *, ahora: datetime | None = None
) -> list[Promocion]:
    """Promociones programadas o vigentes del vuelo, sin las que ya vencieron por fecha."""
    momento = ahora or datetime.now(UTC)
    promociones = db.scalars(
        select(Promocion).where(Promocion.vuelo_id == vuelo_id, Promocion.estado == "programada")
    )
    return [
        promocion
        for promocion in promociones
        if estado_de(promocion, ahora=momento) in ("programada", "vigente")
    ]


def _clases_ocupadas(
    db: Session, vuelo_id: int, clases: Sequence[Clase], *, ahora: datetime
) -> bool:
    """RF-23: ¿alguna de las clases pedidas ya tiene una promoción activa?"""
    pedidas = set(clases)
    return any(
        pedidas.intersection(clases_de(promocion))
        for promocion in _promociones_activas(db, vuelo_id, ahora=ahora)
    )


def _promocion_vigente(
    db: Session, vuelo_id: int, clase: Clase, *, ahora: datetime | None = None
) -> Promocion | None:
    momento = ahora or datetime.now(UTC)
    aplica = Promocion.aplica_economica if clase == "economica" else Promocion.aplica_primera
    promociones = db.scalars(
        select(Promocion).where(
            Promocion.vuelo_id == vuelo_id,
            Promocion.estado == "programada",
            aplica.is_(True),
        )
    )
    for promocion in promociones:
        if estado_de(promocion, ahora=momento) == "vigente":
            return promocion
    return None


def _estado_efectivo_sql(ahora: datetime) -> object:
    """El mismo cálculo de `estado_de`, en SQL, para filtrar y paginar en la base."""
    return case(
        (Promocion.estado.in_(_ESTADOS_TERMINALES), Promocion.estado),
        (Promocion.inicio > ahora, literal("programada")),
        (Promocion.fin > ahora, literal("vigente")),
        else_=literal("vencida"),
    )


def _aplica(promocion: Promocion, clase: Clase) -> bool:
    return promocion.aplica_economica if clase == "economica" else promocion.aplica_primera


def _clases_de_entrada(clases: Sequence[Clase]) -> list[Clase]:
    """Quita clases repetidas y las deja en el orden del contrato."""
    return [clase for clase in ("economica", "primera") if clase in clases]


def _armar_promocion(
    promocion: Promocion,
    vuelo: Vuelo,
    origen: Ciudad,
    destino: Ciudad,
    *,
    ahora: datetime | None = None,
) -> PromocionGestion:
    return PromocionGestion(
        promocion=promocion,
        vuelo=vuelo,
        origen=origen,
        destino=destino,
        clases=clases_de(promocion),
        estado=estado_de(promocion, ahora=ahora),
    )


def _promocion_publicada(
    promocion: Promocion, vuelo: Vuelo, origen: Ciudad, destino: Ciudad
) -> noticias_service.PromocionPublicada:
    """Copia de la promoción para la noticia y el carrusel (RF-25)."""
    return noticias_service.PromocionPublicada(
        promocion_id=promocion.id,
        vuelo=_publicado_de(vuelo, origen, destino),
        porcentaje=promocion.porcentaje,
        clases=tuple(clases_de(promocion)),
        inicio=promocion.inicio,
        fin=promocion.fin,
    )


def _detalle_auditoria_promocion(promocion: Promocion) -> dict[str, object]:
    """Copia serializable de la promoción para la auditoría (RF-26)."""
    return {
        "vuelo_id": promocion.vuelo_id,
        "porcentaje": promocion.porcentaje,
        "clases": clases_de(promocion),
        "inicio": promocion.inicio.isoformat(),
        "fin": promocion.fin.isoformat(),
        "estado": promocion.estado,
    }


def _vuelos_por_id(db: Session, vuelo_ids: set[int]) -> dict[int, Vuelo]:
    """Los vuelos de la página en una sola consulta, sin N+1."""
    if not vuelo_ids:
        return {}
    return {vuelo.id: vuelo for vuelo in db.scalars(select(Vuelo).where(Vuelo.id.in_(vuelo_ids)))}


# El planificador importa los services para que registren sus tareas (HU-18). La guarda evita
# el error de nombre repetido cuando un test reimporta el módulo para comprobar la carga.
if _NOMBRE_TAREA_REALIZADOS not in planificador.tareas:
    registrar_tarea(_NOMBRE_TAREA_REALIZADOS, marcar_realizados, cada=timedelta(minutes=1))

if _NOMBRE_TAREA_VENCER not in planificador.tareas:
    registrar_tarea(_NOMBRE_TAREA_VENCER, vencer_promociones, cada=timedelta(minutes=1))
