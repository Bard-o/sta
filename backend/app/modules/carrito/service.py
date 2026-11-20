"""Interfaz pública del carrito (HU-22, HU-23, RF-30, RF-32, RF-33, SUP-15).

El carrito persiste en la base de datos, no bloquea sillas y cada lectura recalcula el
precio vigente, la disponibilidad, el límite de 5 tiquetes activos y el plazo de venta de
cada tramo. Las selecciones de rutas distintas conviven y no hay tope de selecciones.

Ninguna función hace commit: van en la transacción de quien llama (RNF-17). Las reglas de
los viajeros y la disponibilidad se delegan en `reservas.service` y `vuelos.service`, que son
los dueños de esos datos.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos, NoEncontrado
from app.modules.carrito import schemas
from app.modules.carrito.models import SeleccionCarrito, TramoSeleccion
from app.modules.reservas import service as reservas_service
from app.modules.vuelos import service as vuelos_service

Clase = Literal["economica", "primera"]

# RF-32: la misma regla que aplica al reservar y comprar.
MAXIMO_TIQUETES_POR_VUELO = reservas_service.MAXIMO_TIQUETES_POR_VUELO

# SUP-07, RF-36: una reserva dura 24 horas o hasta el límite de venta del vuelo.
VIGENCIA_RESERVA = reservas_service.VIGENCIA_RESERVA

_NOMBRE_CLASE: dict[Clase, str] = {"economica": "económica", "primera": "primera"}


@dataclass(frozen=True)
class _SeleccionGuardada:
    """Selección leída de la base, con sus tramos en orden de ida y regreso."""

    seleccion: SeleccionCarrito
    tramos: list[TramoSeleccion]


# ---------- Lectura del carrito (HU-23) ----------


def obtener_carrito(
    db: Session, cliente_id: int, *, ahora: datetime | None = None
) -> schemas.Carrito:
    """Carrito del cliente, de la selección más reciente a la más antigua (HU-23, RF-30).

    Cada selección trae el precio y la disponibilidad de hoy, sus avisos y si se puede
    confirmar. `total` suma solo las confirmables; `cantidad` cuenta todas.
    """
    momento = ahora or datetime.now(UTC)
    guardadas = _leer_selecciones(db, cliente_id)
    detalles: dict[int, vuelos_service.VueloDetalleGestion] = {}
    activos: dict[int, int] = {}
    selecciones = [
        _armar_seleccion(db, guardada, momento, detalles, activos) for guardada in guardadas
    ]
    return schemas.Carrito(
        selecciones=selecciones,
        cantidad=len(selecciones),
        total=sum(seleccion.subtotal for seleccion in selecciones if seleccion.confirmable),
    )


# ---------- HU-22: agregar al carrito ----------


def agregar_seleccion(
    db: Session,
    cliente_id: int,
    datos: schemas.SeleccionEntrada,
    *,
    ahora: datetime | None = None,
) -> schemas.SeleccionCarrito:
    """Agrega un trayecto único o completo y valida vuelo, plazo, regreso, límite y cupo.

    No bloquea sillas (SUP-15): la validación es una foto del momento y se repite al
    reservar o comprar. El regreso solo se valida en los trayectos de dos tramos (RF-28).
    """
    momento = ahora or datetime.now(UTC)
    tramos = [(tramo.vuelo_id, tramo.clase) for tramo in datos.tramos]
    detalles = _validar_tramos(
        db, cliente_id, tramos, datos.viajeros, momento=momento, validar_regreso=True
    )

    seleccion = SeleccionCarrito(cliente_id=cliente_id, viajeros=datos.viajeros)
    db.add(seleccion)
    db.flush()
    for orden, ((_, clase), detalle) in enumerate(zip(tramos, detalles, strict=True), start=1):
        db.add(
            TramoSeleccion(
                seleccion_id=seleccion.id,
                vuelo_id=detalle.vuelo.id,
                clase=clase,
                precio_al_agregar=_precio(detalle, clase),
                orden=orden,
            )
        )
    db.flush()
    db.refresh(seleccion)

    cache = {detalle.vuelo.id: detalle for detalle in detalles}
    guardada = _SeleccionGuardada(seleccion, _tramos_de(db, seleccion.id))
    return _armar_seleccion(db, guardada, momento, cache, {})


# ---------- HU-23: modificar y quitar selecciones ----------


def modificar_seleccion(
    db: Session,
    cliente_id: int,
    seleccion_id: int,
    datos: schemas.SeleccionCambio,
    *,
    ahora: datetime | None = None,
) -> schemas.SeleccionCarrito:
    """Cambia la clase o la cantidad de viajeros y vuelve a validar límite y cupo.

    `precio_al_agregar` queda en el precio vigente: el cliente ya vio el cambio. Un cuerpo
    vacío no cambia nada, tal como fija el contrato de HU-23.
    """
    momento = ahora or datetime.now(UTC)
    guardada = _seleccion_del_cliente(db, cliente_id, seleccion_id)
    detalles: dict[int, vuelos_service.VueloDetalleGestion] = {}

    if datos.viajeros is None and datos.clases is None:
        return _armar_seleccion(db, guardada, momento, detalles, {})

    viajeros = guardada.seleccion.viajeros if datos.viajeros is None else datos.viajeros
    clases = (
        [tramo.clase for tramo in guardada.tramos] if datos.clases is None else list(datos.clases)
    )
    if len(clases) != len(guardada.tramos):
        raise DatosInvalidos(campos={"clases": "Debe traer una clase por cada tramo."})

    for tramo, clase in zip(guardada.tramos, clases, strict=True):
        reservas_service.validar_limite_de_tiquetes(db, cliente_id, tramo.vuelo_id, viajeros)
        reservas_service.validar_cupo(db, tramo.vuelo_id, clase, viajeros)

    guardada.seleccion.viajeros = viajeros
    for tramo, clase in zip(guardada.tramos, clases, strict=True):
        detalle = _detalle(db, tramo.vuelo_id, momento, detalles)
        tramo.clase = clase
        tramo.precio_al_agregar = _precio(detalle, clase)
    db.flush()

    return _armar_seleccion(db, guardada, momento, detalles, {})


def quitar_seleccion(db: Session, cliente_id: int, seleccion_id: int) -> None:
    """Quita una selección del carrito; el borrado de sus tramos va en cascada (HU-23)."""
    guardada = _seleccion_del_cliente(db, cliente_id, seleccion_id)
    db.delete(guardada.seleccion)
    db.flush()


def vaciar_carrito(db: Session, cliente_id: int) -> None:
    """Quita todas las selecciones del cliente; vaciar un carrito vacío no falla (HU-23)."""
    db.execute(delete(SeleccionCarrito).where(SeleccionCarrito.cliente_id == cliente_id))
    db.flush()


# ---------- Validaciones de HU-22 ----------


def _validar_tramos(
    db: Session,
    cliente_id: int,
    tramos: Sequence[tuple[int, Clase]],
    viajeros: int,
    *,
    momento: datetime,
    validar_regreso: bool,
) -> list[vuelos_service.VueloDetalleGestion]:
    """Reglas de HU-22 en el orden del contrato: vuelo, plazo, regreso, límite y cupo."""
    detalles: list[vuelos_service.VueloDetalleGestion] = []
    for indice, (vuelo_id, _) in enumerate(tramos):
        try:
            detalle = vuelos_service.obtener_vuelo_detalle(db, vuelo_id, ahora=momento)
        except NoEncontrado:
            raise _vuelo_no_disponible(indice) from None
        if detalle.vuelo.estado != "programado":
            raise _vuelo_no_disponible(indice)
        if momento >= vuelos_service.limite_de_venta(detalle.vuelo.tipo, detalle.vuelo.salida):
            raise _fuera_de_plazo(indice, detalle.vuelo)
        detalles.append(detalle)

    if validar_regreso:
        _validar_regreso(detalles)

    for (vuelo_id, clase), _ in zip(tramos, detalles, strict=True):
        reservas_service.validar_limite_de_tiquetes(db, cliente_id, vuelo_id, viajeros)
        reservas_service.validar_cupo(db, vuelo_id, clase, viajeros)
    return detalles


def _validar_regreso(detalles: Sequence[vuelos_service.VueloDetalleGestion]) -> None:
    """RF-28: el regreso es otro vuelo y sale del destino de la ida después de su llegada.

    «Después» es estricto (`<=` rechaza), como en la búsqueda de regresos (HU-21) y en
    `reservas.service`: un regreso que sale en el mismo instante en que aterriza la ida no se
    puede abordar y responde `regreso_invalido`. La regla vive en `reservas.service` como
    función privada; el carrito la aplica con los detalles públicos de `vuelos.service` y lanza
    la misma excepción del contrato.
    """
    if len(detalles) != 2:
        return
    ida, regreso = detalles
    if (
        regreso.vuelo.id == ida.vuelo.id
        or regreso.vuelo.origen_codigo != ida.vuelo.destino_codigo
        or regreso.vuelo.salida <= ida.vuelo.llegada
    ):
        raise reservas_service.RegresoInvalido(
            f"El regreso debe salir de {ida.destino.nombre} después de la llegada de la ida.",
            campos={"tramos.1.vuelo_id": "Elige un regreso que salga después de tu llegada."},
        )


def _vuelo_no_disponible(indice: int) -> reservas_service.VueloNoDisponible:
    return reservas_service.VueloNoDisponible(
        campos={f"tramos.{indice}.vuelo_id": "El vuelo no existe o ya no está programado."}
    )


def _fuera_de_plazo(indice: int, vuelo: object) -> reservas_service.FueraDePlazo:
    horas = 1 if vuelo.tipo == "nacional" else 3
    otras = 3 if horas == 1 else 1
    return reservas_service.FueraDePlazo(
        f"La venta de {vuelo.codigo} ya cerró: cierra {horas} "
        f"{'hora' if horas == 1 else 'horas'} antes de la salida ({otras} "
        f"{'hora' if otras == 1 else 'horas'} si es "
        f"{'internacional' if horas == 1 else 'nacional'}).",
        campos={f"tramos.{indice}.vuelo_id": "Ya no se puede reservar ni comprar."},
    )


# ---------- Armado de una selección ----------


def _armar_seleccion(
    db: Session,
    guardada: _SeleccionGuardada,
    momento: datetime,
    detalles: dict[int, vuelos_service.VueloDetalleGestion],
    activos: dict[int, int],
) -> schemas.SeleccionCarrito:
    """Recalcula una selección con el precio y la disponibilidad de `momento` (HU-23)."""
    avisos: list[schemas.AvisoSeleccion] = []
    tramos: list[schemas.TramoCarrito] = []
    limites: list[datetime] = []

    for indice, tramo in enumerate(guardada.tramos):
        detalle = _detalle(db, tramo.vuelo_id, momento, detalles)
        clase_detalle = _clase_detalle(detalle, tramo.clase)
        vuelo = detalle.vuelo
        tiquetes_activos = _tiquetes_activos(db, guardada.seleccion.cliente_id, vuelo.id, activos)
        limite = vuelos_service.limite_de_venta(vuelo.tipo, vuelo.salida)

        if vuelo.estado != "programado":
            avisos.append(
                _aviso(
                    "vuelo_no_disponible",
                    f"{vuelo.codigo} ya no está a la venta: se canceló o ya se realizó.",
                    indice,
                )
            )
        elif momento >= limite:
            avisos.append(_aviso("fuera_de_plazo", f"La venta de {vuelo.codigo} ya cerró.", indice))
        else:
            if clase_detalle.precio != tramo.precio_al_agregar:
                avisos.append(
                    _aviso(
                        "precio_cambio",
                        f"El precio cambió de {_pesos(tramo.precio_al_agregar)} a "
                        f"{_pesos(clase_detalle.precio)}. Pagarás el precio nuevo.",
                        indice,
                    )
                )
            if tiquetes_activos + guardada.seleccion.viajeros > MAXIMO_TIQUETES_POR_VUELO:
                avisos.append(
                    _aviso(
                        "limite_tiquetes",
                        f"Ya tienes {tiquetes_activos} tiquetes activos en {vuelo.codigo} y "
                        f"el máximo por vuelo es {MAXIMO_TIQUETES_POR_VUELO}.",
                        indice,
                    )
                )
            if clase_detalle.disponibles < guardada.seleccion.viajeros:
                avisos.append(
                    _aviso(
                        "clase_agotada",
                        f"Ya no quedan sillas suficientes en {_NOMBRE_CLASE[tramo.clase]}. "
                        "Cambia de clase o quita este vuelo.",
                        indice,
                    )
                )
        limites.append(limite)

        tramos.append(
            schemas.TramoCarrito(
                vuelo=_vuelo_carrito(detalle),
                clase=tramo.clase,
                precio_unitario=clase_detalle.precio,
                precio_al_agregar=tramo.precio_al_agregar,
                promocion_porcentaje=(
                    clase_detalle.promocion.porcentaje
                    if clase_detalle.promocion is not None
                    else None
                ),
                disponibles=clase_detalle.disponibles,
                tiquetes_activos=tiquetes_activos,
            )
        )

    confirmable = all(aviso.codigo == "precio_cambio" for aviso in avisos)
    vence_en = min(momento + VIGENCIA_RESERVA, *limites) if confirmable and limites else None
    return schemas.SeleccionCarrito(
        id=guardada.seleccion.id,
        tramos=tramos,
        viajeros=guardada.seleccion.viajeros,
        subtotal=sum(tramo.precio_unitario for tramo in tramos) * guardada.seleccion.viajeros,
        confirmable=confirmable,
        avisos=avisos,
        reserva_venceria_en=vence_en,
        agregada_en=guardada.seleccion.creado_en,
    )


# ---------- Consultas y conversiones ----------


def _leer_selecciones(db: Session, cliente_id: int) -> list[_SeleccionGuardada]:
    """Selecciones del cliente y sus tramos, en dos consultas y sin N+1.

    El desempate por id importa: `now()` de PostgreSQL es la hora de la transacción y
    varias selecciones creadas en la misma transacción comparten `creado_en`.
    """
    selecciones = list(
        db.scalars(
            select(SeleccionCarrito)
            .where(SeleccionCarrito.cliente_id == cliente_id)
            .order_by(SeleccionCarrito.creado_en.desc(), SeleccionCarrito.id.desc())
        )
    )
    if not selecciones:
        return []

    tramos: dict[int, list[TramoSeleccion]] = {seleccion.id: [] for seleccion in selecciones}
    for tramo in db.scalars(
        select(TramoSeleccion)
        .where(TramoSeleccion.seleccion_id.in_(list(tramos)))
        .order_by(TramoSeleccion.seleccion_id, TramoSeleccion.orden)
    ):
        tramos[tramo.seleccion_id].append(tramo)
    return [_SeleccionGuardada(seleccion, tramos[seleccion.id]) for seleccion in selecciones]


def _seleccion_del_cliente(db: Session, cliente_id: int, seleccion_id: int) -> _SeleccionGuardada:
    """Selección del cliente o `404 no_encontrado`; un id ajeno se ve igual que uno inexistente."""
    seleccion = db.scalar(
        select(SeleccionCarrito).where(
            SeleccionCarrito.id == seleccion_id,
            SeleccionCarrito.cliente_id == cliente_id,
        )
    )
    if seleccion is None:
        raise NoEncontrado("La selección no existe.")
    return _SeleccionGuardada(seleccion, _tramos_de(db, seleccion.id))


def _tramos_de(db: Session, seleccion_id: int) -> list[TramoSeleccion]:
    return list(
        db.scalars(
            select(TramoSeleccion)
            .where(TramoSeleccion.seleccion_id == seleccion_id)
            .order_by(TramoSeleccion.orden)
        )
    )


def _detalle(
    db: Session,
    vuelo_id: int,
    momento: datetime,
    cache: dict[int, vuelos_service.VueloDetalleGestion],
) -> vuelos_service.VueloDetalleGestion:
    """Detalle del vuelo cacheado por petición: precio, promoción y disponibilidad."""
    if vuelo_id not in cache:
        cache[vuelo_id] = vuelos_service.obtener_vuelo_detalle(db, vuelo_id, ahora=momento)
    return cache[vuelo_id]


def _tiquetes_activos(db: Session, cliente_id: int, vuelo_id: int, cache: dict[int, int]) -> int:
    """Tiquetes activos del cliente en el vuelo, cacheados por petición (RF-32)."""
    if vuelo_id not in cache:
        cache[vuelo_id] = reservas_service.tiquetes_activos_en_vuelo(db, cliente_id, vuelo_id)
    return cache[vuelo_id]


def _clase_detalle(
    detalle: vuelos_service.VueloDetalleGestion, clase: Clase
) -> vuelos_service.ClaseDetalleVuelo:
    return detalle.primera if clase == "primera" else detalle.economica


def _precio(detalle: vuelos_service.VueloDetalleGestion, clase: Clase) -> int:
    return _clase_detalle(detalle, clase).precio


def _vuelo_carrito(detalle: vuelos_service.VueloDetalleGestion) -> schemas.VueloCarrito:
    vuelo = detalle.vuelo
    return schemas.VueloCarrito(
        id=vuelo.id,
        codigo=vuelo.codigo,
        tipo=vuelo.tipo,
        origen=schemas.CiudadCarrito(
            codigo=detalle.origen.codigo,
            nombre=detalle.origen.nombre,
            zona_horaria=detalle.origen.zona_horaria,
        ),
        destino=schemas.CiudadCarrito(
            codigo=detalle.destino.codigo,
            nombre=detalle.destino.nombre,
            zona_horaria=detalle.destino.zona_horaria,
        ),
        salida=vuelo.salida,
        llegada=vuelo.llegada,
        duracion_minutos=vuelo.duracion_minutos,
        estado=vuelo.estado,
    )


def _aviso(codigo: str, mensaje: str, tramo: int) -> schemas.AvisoSeleccion:
    return schemas.AvisoSeleccion(codigo=codigo, mensaje=mensaje, tramo=tramo)


def _pesos(valor: int) -> str:
    """COP con separador de miles de punto, como en la interfaz (IU-06)."""
    return f"$ {valor:,}".replace(",", ".")
