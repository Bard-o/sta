"""Interfaz pública del módulo vuelos. Otros módulos solo llaman a estas funciones.

Concentra la lógica que comparten programar, editar y las series: catálogo de ciudades,
rutas permitidas, conversión de la hora local del origen a UTC, llegada, tipo y capacidad
(RF-12 a RF-16). Ninguna función hace commit: van en la transacción de quien llama.
"""

import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos, NoEncontrado
from app.modules.auditoria import service as auditoria_service
from app.modules.noticias import service as noticias_service
from app.modules.reservas import service as reservas_service
from app.modules.vuelos.models import Ciudad, EstadoVuelo, TipoVuelo, Vuelo
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
# Motivos que ve el administrador cuando el vuelo no se puede editar (HU-15).
_MOTIVO_CERRADO = "El vuelo ya se realizó o está cancelado."
_MOTIVO_SALIO = "El vuelo ya salió."
_MOTIVO_VENTAS = "El vuelo tiene reservas activas o compras."


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
class PaginaVuelosGestion:
    """Página del listado del administrador (HU-15, HU-16, HU-18)."""

    items: list[VueloGestion]
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
    return noticias_service.VueloPublicado(
        vuelo_id=vuelo.id,
        codigo=vuelo.codigo,
        origen=_ciudad_publicada(calculado.origen),
        destino=_ciudad_publicada(calculado.destino),
        salida=vuelo.salida,
        precio_economica=vuelo.precio_economica,
        precio_primera=vuelo.precio_primera,
        imagen_url=calculado.destino.imagen_url,
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
