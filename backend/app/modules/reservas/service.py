"""Interfaz pública del módulo reservas. Otros módulos solo llaman a estas funciones.

Aquí viven las reglas de los viajeros (RF-31 a RF-35), la creación de una reserva (HU-24,
RF-36, RF-41 y RF-42), el vencimiento automático (RF-37) y la anulación al cancelar un vuelo
(HU-16), además de las consultas que usan vuelos, usuarios y carrito. La compra (#124) y el
trayecto completo (#130) reutilizan estas mismas piezas.

Ninguna función hace commit: van en la transacción de quien llama.
"""

import random
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, distinct, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos, NoAutenticado, NoEncontrado
from app.core.mail import Adjunto, encolar_correo
from app.core.planificador import registrar_tarea
from app.modules.reservas.comprobante import (
    DatosComprobante,
    TiqueteComprobante,
    TramoComprobante,
    ViajeroComprobante,
    generar_comprobante,
)
from app.modules.reservas.models import (
    ESTADOS_TIQUETE_ACTIVOS,
    Clase,
    EstadoTiquete,
    Tiquete,
    Tramo,
    Transaccion,
    Viajero,
)
from app.modules.reservas.schemas import (
    CiudadViaje,
    TiqueteViaje,
    TramoViaje,
    Viaje,
    ViajeEntrada,
    ViajeroViaje,
    VueloViaje,
)
from app.modules.reservas.sillas import SillasInsuficientes, asignar_sillas

# RF-32: máximo de tiquetes activos de un cliente en un mismo vuelo, sumando clases.
MAXIMO_TIQUETES_POR_VUELO = 5

# RF-36: la reserva dura 24 horas o hasta el límite de venta del vuelo, lo que ocurra primero.
VIGENCIA_RESERVA = timedelta(hours=24)

# SUP-15: la compra bloquea las sillas 15 minutos o hasta el límite de venta del vuelo.
BLOQUEO_COMPRA = timedelta(minutes=15)

# RF-37, RNF-18: nombre de la tarea programada que vence las reservas.
NOMBRE_TAREA_VENCER = "reservas.vencer_reservas"
# SUP-15, RNF-18: nombre de la tarea programada que libera los bloqueos de las compras.
NOMBRE_TAREA_LIBERAR = "reservas.liberar_bloqueos"

# RF-42: las asignaciones de un vuelo se serializan con un lock de asesoría por vuelo.
# Es la primera clave del par; la segunda es el id del vuelo.
_CLAVE_LOCK_VUELOS = 1_240

# RF-39: código alfanumérico de 6 caracteres sin letras ni dígitos que se confunden.
_CODIGO_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODIGO_LARGO = 6
# RF-42: si otra transacción tomó las sillas, se reintenta la asignación en la misma petición.
_INTENTOS_DE_ASIGNACION = 3

# RF-31: mismo patrón que usa el registro de usuarios para el correo.
_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GENEROS = ("femenino", "masculino", "otro")
# La fecha de nacimiento se mide con la fecha local de Colombia, igual que en usuarios.
_ZONA_NEGOCIO = ZoneInfo("America/Bogota")


class LimiteDeTiquetes(Conflicto):
    """RF-32: el cliente ya tiene 5 tiquetes activos en el vuelo."""

    codigo = "limite_tiquetes"
    mensaje = "Un cliente puede tener máximo 5 tiquetes activos en el mismo vuelo."


class ViajeroDuplicado(Conflicto):
    """RF-34: el documento ya tiene un tiquete activo en el vuelo.

    El mensaje no dice quién hizo la otra compra ni a qué transacción pertenece.
    """

    codigo = "viajero_duplicado"
    mensaje = "Uno de los documentos ya tiene un tiquete activo en este vuelo."


class MenorSinAdulto(DatosInvalidos):
    """RF-35: un menor no puede viajar sin un adulto en el mismo vuelo."""

    codigo = "menor_sin_adulto"
    mensaje = "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo."


class VueloNoDisponible(Conflicto):
    """HU-24: el vuelo no existe, está cancelado o ya se realizó."""

    codigo = "vuelo_no_disponible"
    mensaje = "Uno de los vuelos ya no está a la venta."


class FueraDePlazo(Conflicto):
    """SUP-07, RF-36: ya pasó el límite de venta del vuelo."""

    codigo = "fuera_de_plazo"
    mensaje = "La venta del vuelo ya cerró."


class RegresoInvalido(DatosInvalidos):
    """RF-28, HU-26: el regreso no sale del destino de la ida o sale antes de su llegada."""

    codigo = "regreso_invalido"
    mensaje = "El regreso debe salir del destino de la ida después de su llegada."


class CompraNoEncontrada(NoEncontrado):
    """HU-25: la compra no existe o es de otro cliente."""

    mensaje = "La compra no existe."


class EstadoInvalido(Conflicto):
    """HU-25: confirmar o soltar una compra que ya está pagada."""

    codigo = "estado_invalido"
    mensaje = "La compra ya está pagada."


class BloqueoVencido(Conflicto):
    """SUP-15: el bloqueo de 15 minutos de la compra venció o se soltó."""

    codigo = "bloqueo_vencido"
    mensaje = (
        "Las sillas se liberaron porque pasaron 15 minutos sin confirmar. "
        "Vuelve a empezar la compra."
    )


@dataclass(frozen=True)
class ViajeroParaValidar:
    """Datos mínimos de un viajero para aplicar las reglas de RF-31 a RF-35.

    Es un contrato de entrada del service, independiente de los schemas de la API. #118 y
    #124 convierten su `ViajeroEntrada` a esta forma antes de llamar a las reglas.
    """

    tipo_documento: str
    numero_documento: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None
    genero: str
    telefono: str
    email: str
    contacto_nombre: str
    contacto_telefono: str


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


# ---------- Consultas públicas (HU-09, HU-15, HU-16, HU-18, HU-22) ----------


def ocupacion_de_vuelos(db: Session, vuelo_ids: Sequence[int]) -> dict[int, OcupacionVuelo]:
    """Ventas y reservas vigentes por vuelo, en una sola consulta (HU-15, HU-16, HU-18).

    Devuelve una entrada por cada id pedido, aunque no tenga ventas. Los tiquetes
    `bloqueado` y `reservado` cuentan como reservadas; los `comprado`, como vendidas. Los
    cancelados, vencidos, reembolsados y reubicados no ocupan silla (RF-32, RF-34).
    `reservas_activas` cuenta las reservas vigentes y las compras pendientes: ambas impiden
    editar o cancelar el vuelo sin anularlas (HU-15, HU-16).
    """
    if not vuelo_ids:
        return {}

    valores: dict[int, dict[str, int]] = {
        vuelo_id: {
            "vendidas_primera": 0,
            "vendidas_economica": 0,
            "reservadas_primera": 0,
            "reservadas_economica": 0,
            "reservas_activas": 0,
        }
        for vuelo_id in set(vuelo_ids)
    }

    filas = db.execute(
        select(
            Tiquete.vuelo_id,
            Tramo.clase,
            func.count().filter(Tiquete.estado == "comprado").label("vendidas"),
            func.count().filter(Tiquete.estado.in_(("bloqueado", "reservado"))).label("reservadas"),
            func.count(distinct(Tramo.transaccion_id))
            .filter(
                or_(
                    and_(Transaccion.tipo == "reserva", Transaccion.estado == "vigente"),
                    and_(Transaccion.tipo == "compra", Transaccion.estado == "pendiente"),
                )
            )
            .label("reservas_activas"),
        )
        .join(Tramo, Tiquete.tramo_id == Tramo.id)
        .join(Transaccion, Tramo.transaccion_id == Transaccion.id)
        .where(
            Tiquete.vuelo_id.in_(vuelo_ids),
            Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS),
        )
        .group_by(Tiquete.vuelo_id, Tramo.clase)
    ).all()

    for vuelo_id, clase, vendidas, reservadas, reservas_activas in filas:
        acumulado = valores[vuelo_id]
        acumulado[f"vendidas_{clase}"] += vendidas
        acumulado[f"reservadas_{clase}"] += reservadas
        # El conteo se repite en cada clase del mismo vuelo; no se suma dos veces.
        acumulado["reservas_activas"] = max(acumulado["reservas_activas"], reservas_activas)

    return {vuelo_id: OcupacionVuelo(**valores[vuelo_id]) for vuelo_id in set(vuelo_ids)}


def anular_reservas_de_vuelo(db: Session, vuelo_id: int) -> int:
    """Anula las reservas vigentes y las compras pendientes del vuelo (HU-16).

    Sus tiquetes pasan a `cancelado` (liberan las sillas), encola el correo a cada cliente y
    devuelve cuántas anuló. No hace commit. Es idempotente: la segunda vez no encuentra nada.
    """
    from app.modules.vuelos import service as vuelos_service

    ids = list(
        db.scalars(
            select(Transaccion.id)
            .join(Tramo, Tramo.transaccion_id == Transaccion.id)
            .where(
                Tramo.vuelo_id == vuelo_id,
                or_(
                    and_(Transaccion.tipo == "reserva", Transaccion.estado == "vigente"),
                    and_(Transaccion.tipo == "compra", Transaccion.estado == "pendiente"),
                ),
            )
            .distinct()
        )
    )
    if not ids:
        return 0

    transacciones = list(
        db.scalars(
            select(Transaccion)
            .where(Transaccion.id.in_(ids))
            .order_by(Transaccion.id)
            .with_for_update()
        )
    )
    try:
        codigo_vuelo = vuelos_service.obtener_vuelo_detalle(db, vuelo_id).vuelo.codigo
    except NoEncontrado:
        codigo_vuelo = "el vuelo"

    for transaccion in transacciones:
        transaccion.estado = "cancelada"
        _cambiar_estado_de_tiquetes(db, transaccion.id, "cancelado")
        nombre = "reserva" if transaccion.tipo == "reserva" else "compra"
        _encolar_aviso(
            db,
            transaccion,
            f"Tu {nombre} {transaccion.codigo} se canceló",
            f"Tu {nombre} {transaccion.codigo} se canceló porque el vuelo {codigo_vuelo} "
            "fue cancelado. No se hizo ningún cobro.",
        )
    db.flush()
    return len(transacciones)


# ---------- Reserva (HU-24, RF-36 a RF-42) ----------


def crear_reserva(
    db: Session, usuario_id: int, datos: ViajeEntrada, *, ahora: datetime | None = None
) -> Transaccion:
    """Crea una reserva sin cobrar: asigna sillas, congela el precio y fija el vencimiento.

    Aplica las reglas del contrato en su orden (HU-24): correo verificado, vuelo vendible,
    regreso válido, datos y clases, documento duplicado, menores, límite de 5 y cupo. Las
    asignaciones de un mismo vuelo se serializan con un lock de asesoría y los índices únicos
    parciales de `tiquetes` resuelven la carrera por las últimas sillas (RF-42). No hace
    commit: el endpoint o el test confirman la transacción.
    """
    return _crear_viaje(db, usuario_id, datos, tipo="reserva", ahora=ahora)


def crear_compra(
    db: Session, usuario_id: int, datos: ViajeEntrada, *, ahora: datetime | None = None
) -> Transaccion:
    """Inicia una compra: asigna las sillas, congela el precio y las bloquea 15 minutos.

    Usa las mismas reglas de HU-24 que la reserva (RF-31 a RF-35, RF-41 y RF-42), pero deja
    la compra `pendiente`, sus tiquetes `bloqueado` y `bloqueo_hasta` con el fin de la ventana
    de pago (SUP-15). No cobra ni hace commit.
    """
    return _crear_viaje(db, usuario_id, datos, tipo="compra", ahora=ahora)


def _crear_viaje(
    db: Session,
    usuario_id: int,
    datos: ViajeEntrada,
    *,
    tipo: Literal["compra", "reserva"],
    ahora: datetime | None,
) -> Transaccion:
    """Reglas comunes de reservar y comprar, en el orden del contrato (HU-24 a HU-26)."""
    from app.modules.vuelos import service as vuelos_service

    momento = ahora or datetime.now(UTC)
    _exigir_correo_verificado(db, usuario_id)
    detalles = _bloquear_y_validar_tramos(db, datos, momento)
    _validar_regreso(detalles)
    _validar_clases(datos)
    viajeros = [_a_viajero_para_validar(viajero) for viajero in datos.viajeros]
    validar_viajeros(viajeros, hoy=momento.astimezone(_ZONA_NEGOCIO).date())

    # El contrato fija el orden: primero todos los documentos, luego los menores, el límite y
    # el cupo, aunque haya dos tramos (HU-24, HU-26).
    for detalle in detalles:
        validar_documentos_en_vuelo(db, detalle.vuelo.id, viajeros)
    for detalle in detalles:
        validar_menores(db, detalle.vuelo.id, viajeros)
    for detalle in detalles:
        validar_limite_de_tiquetes(db, usuario_id, detalle.vuelo.id, len(viajeros))
    for indice, detalle in enumerate(detalles):
        for clase in ("primera", "economica"):
            cantidad = sum(1 for viajero in datos.viajeros if viajero.clases[indice] == clase)
            validar_cupo(db, detalle.vuelo.id, clase, cantidad)

    limite_de_venta = min(
        vuelos_service.limite_de_venta(detalle.vuelo.tipo, detalle.vuelo.salida)
        for detalle in detalles
    )
    if tipo == "reserva":
        vence_en: datetime | None = min(momento + VIGENCIA_RESERVA, limite_de_venta)
        bloqueo_hasta = None
        estado = "vigente"
        estado_tiquete: EstadoTiquete = "reservado"
    else:
        vence_en = None
        bloqueo_hasta = min(momento + BLOQUEO_COMPRA, limite_de_venta)
        estado = "pendiente"
        estado_tiquete = "bloqueado"

    return _insertar_transaccion(
        db,
        usuario_id,
        datos,
        detalles,
        momento,
        tipo=tipo,
        estado=estado,
        vence_en=vence_en,
        bloqueo_hasta=bloqueo_hasta,
        estado_tiquete=estado_tiquete,
    )


def viaje_de(db: Session, transaccion: Transaccion) -> Viaje:
    """Forma pública de una reserva o compra (HU-24 a HU-27).

    La usan este endpoint y los de #124, #130 y #131 para responder siempre la misma forma.
    """
    from app.modules.vuelos import service as vuelos_service

    if transaccion.creado_en is None:
        db.refresh(transaccion)

    tramos = list(
        db.scalars(
            select(Tramo)
            .where(Tramo.transaccion_id == transaccion.id)
            .order_by(Tramo.orden, Tramo.clase)
        )
    )
    viajeros = list(
        db.scalars(
            select(Viajero).where(Viajero.transaccion_id == transaccion.id).order_by(Viajero.id)
        )
    )
    tramos_por_id = {tramo.id: tramo for tramo in tramos}
    tiquetes = (
        list(db.scalars(select(Tiquete).where(Tiquete.tramo_id.in_(list(tramos_por_id)))))
        if tramos_por_id
        else []
    )

    # Un tramo de la respuesta por vuelo (ida y regreso), aunque haya dos clases en el mismo.
    por_orden: dict[int, Tramo] = {}
    for tramo in tramos:
        por_orden.setdefault(tramo.orden, tramo)
    ordenes = sorted(por_orden)
    detalles = {
        orden: vuelos_service.obtener_vuelo_detalle(db, por_orden[orden].vuelo_id)
        for orden in ordenes
    }
    indice_de_vuelo = {detalles[orden].vuelo.id: indice for indice, orden in enumerate(ordenes)}

    tiquetes_por_viajero: dict[int, list[TiqueteViaje]] = {viajero.id: [] for viajero in viajeros}
    for tiquete in tiquetes:
        tramo = tramos_por_id[tiquete.tramo_id]
        detalle = detalles[tramo.orden]
        tiquetes_por_viajero[tiquete.viajero_id].append(
            TiqueteViaje(
                id=tiquete.id,
                tramo=indice_de_vuelo[tiquete.vuelo_id],
                clase=tramo.clase,
                silla=vuelos_service.nombre_de_silla(
                    detalle.vuelo.tipo, tramo.clase, tiquete.numero_silla
                ),
                numero_silla=tiquete.numero_silla,
                precio=tramo.precio,
                estado=tiquete.estado,
            )
        )
    for lista in tiquetes_por_viajero.values():
        lista.sort(key=lambda tiquete: tiquete.tramo)

    total = sum(tramos_por_id[tiquete.tramo_id].precio for tiquete in tiquetes)
    total_pendiente = sum(
        tramos_por_id[tiquete.tramo_id].precio
        for tiquete in tiquetes
        if tiquete.estado in ("bloqueado", "reservado")
    )

    # HU-24: una reserva vence en `vence_en`; una compra, al final de su bloqueo, salvo que ya
    # esté pagada. El contrato llama `vence_en` a las dos fechas.
    if transaccion.tipo == "reserva":
        vence_en = transaccion.vence_en
    elif transaccion.estado == "activa":
        vence_en = None
    else:
        vence_en = transaccion.bloqueo_hasta

    return Viaje(
        id=transaccion.id,
        tipo=transaccion.tipo,
        codigo=transaccion.codigo or "",
        estado=transaccion.estado,
        reserva_id=None,
        compra_id=None,
        creada_en=transaccion.creado_en,
        vence_en=vence_en,
        pagada_en=transaccion.pagada_en,
        total=total,
        total_pendiente=total_pendiente,
        tramos=[TramoViaje(vuelo=_vuelo_viaje(detalles[orden])) for orden in ordenes],
        viajeros=[
            ViajeroViaje(
                id=viajero.id,
                tipo_documento=viajero.tipo_documento,
                numero_documento=viajero.numero_documento,
                nombres=viajero.nombres,
                apellidos=viajero.apellidos,
                fecha_nacimiento=viajero.fecha_nacimiento,
                genero=viajero.genero,
                telefono=viajero.telefono,
                email=viajero.email,
                contacto_nombre=viajero.contacto_nombre,
                contacto_telefono=viajero.contacto_telefono,
                tiquetes=tiquetes_por_viajero[viajero.id],
            )
            for viajero in viajeros
        ],
    )


def vencer_reservas(db: Session, ahora: datetime) -> int:
    """Vence las reservas cuyo plazo pasó (RF-37, RNF-18).

    Las deja `vencida`, pasa sus tiquetes a `vencido` (liberan las sillas) y encola el correo
    al cliente. Procesa todo lo vencido hasta `ahora`, es idempotente y no hace commit: la
    ejecuta el planificador cada minuto.
    """
    reservas = list(
        db.scalars(
            select(Transaccion)
            .where(
                Transaccion.tipo == "reserva",
                Transaccion.estado == "vigente",
                Transaccion.vence_en <= ahora,
            )
            .order_by(Transaccion.id)
            .with_for_update(skip_locked=True)
        )
    )
    for reserva in reservas:
        reserva.estado = "vencida"
        _cambiar_estado_de_tiquetes(db, reserva.id, "vencido")
        _encolar_aviso(
            db,
            reserva,
            f"Tu reserva {reserva.codigo} venció",
            f"Tu reserva {reserva.codigo} venció y las sillas quedaron libres. "
            "Si todavía quieres viajar, vuelve a reservar.",
        )
    db.flush()
    return len(reservas)


# ---------- Compra (HU-25, RF-39 a RF-42, SUP-15) ----------


def obtener_compra(
    db: Session, usuario_id: int, compra_id: int, *, ahora: datetime | None = None
) -> Transaccion:
    """Una compra del cliente en su estado efectivo (HU-25).

    Si el bloqueo ya venció, la deja `vencida` y sus tiquetes `vencido` antes de responder:
    el contrato informa el vencimiento a su hora aunque el planificador no haya corrido.
    """
    momento = ahora or datetime.now(UTC)
    compra = _compra_del_cliente(db, usuario_id, compra_id, para_actualizar=True)
    if compra.estado == "pendiente" and _bloqueo_vencido(compra, momento):
        _vencer_compra(db, compra)
        db.flush()
    return compra


def confirmar_compra(
    db: Session, usuario_id: int, compra_id: int, *, ahora: datetime | None = None
) -> Transaccion:
    """Cobra la compra con el monedero y emite los tiquetes (HU-25, RNF-17).

    Todo ocurre en la transacción de quien llama: el débito, los tiquetes, el estado, los
    correos y las promociones agotadas. Si algo falla no queda nada. Los bloqueos vigentes
    impiden que otra petición tome las sillas, así que aquí no se reasignan.
    """
    from app.modules.monedero import service as monedero_service
    from app.modules.vuelos import service as vuelos_service

    momento = ahora or datetime.now(UTC)
    compra = _compra_del_cliente(db, usuario_id, compra_id, para_actualizar=True)
    _exigir_correo_verificado(db, usuario_id)

    if compra.estado == "activa":
        raise EstadoInvalido()
    if compra.estado != "pendiente" or _bloqueo_vencido(compra, momento):
        raise BloqueoVencido()

    total = _total_pendiente(db, compra)
    if total <= 0:
        raise EstadoInvalido()
    codigo = compra.codigo or ""
    monedero_service.debitar(db, usuario_id, total, referencia=codigo)

    _cambiar_estado_de_tiquetes(db, compra.id, "comprado")
    compra.estado = "activa"
    compra.pagada_en = momento
    db.flush()

    _enviar_correos_de_compra(db, compra, momento)
    for vuelo_id in _vuelos_de_transaccion(db, compra.id):
        vuelos_service.marcar_promociones_agotadas(db, vuelo_id, ahora=momento)
    db.flush()
    return compra


def soltar_compra(
    db: Session, usuario_id: int, compra_id: int, *, ahora: datetime | None = None
) -> None:
    """Suelta el bloqueo de una compra pendiente y libera sus sillas (HU-25).

    Una compra ya cancelada o vencida responde sin cambios; una pagada es `estado_invalido`.
    No hace commit: el endpoint confirma.
    """
    momento = ahora or datetime.now(UTC)
    compra = _compra_del_cliente(db, usuario_id, compra_id, para_actualizar=True)
    if compra.estado == "activa":
        raise EstadoInvalido()
    if compra.estado == "pendiente":
        if _bloqueo_vencido(compra, momento):
            _vencer_compra(db, compra)
        else:
            compra.estado = "cancelada"
            _cambiar_estado_de_tiquetes(db, compra.id, "cancelado")
        db.flush()
    elif compra.estado not in ("cancelada", "vencida"):
        raise EstadoInvalido()


def liberar_bloqueos(db: Session, ahora: datetime) -> int:
    """Vence las compras cuyo bloqueo de 15 minutos pasó y libera sus sillas (SUP-15).

    Procesa todo lo vencido hasta `ahora`, es idempotente y no hace commit: la ejecuta el
    planificador cada minuto, también al arrancar el servidor (RNF-18).
    """
    compras = list(
        db.scalars(
            select(Transaccion)
            .where(
                Transaccion.tipo == "compra",
                Transaccion.estado == "pendiente",
                Transaccion.bloqueo_hasta <= ahora,
            )
            .order_by(Transaccion.id)
            .with_for_update(skip_locked=True)
        )
    )
    for compra in compras:
        _vencer_compra(db, compra)
    db.flush()
    return len(compras)


def _compra_del_cliente(
    db: Session, usuario_id: int, compra_id: int, *, para_actualizar: bool
) -> Transaccion:
    """Compra del cliente; 404 si no existe, es de otro o es una reserva."""
    consulta = select(Transaccion).where(
        Transaccion.id == compra_id,
        Transaccion.cliente_id == usuario_id,
        Transaccion.tipo == "compra",
    )
    if para_actualizar:
        consulta = consulta.with_for_update()
    compra = db.scalar(consulta)
    if compra is None:
        raise CompraNoEncontrada()
    return compra


def _bloqueo_vencido(compra: Transaccion, ahora: datetime) -> bool:
    return compra.bloqueo_hasta is None or compra.bloqueo_hasta <= ahora


def _vencer_compra(db: Session, compra: Transaccion) -> None:
    compra.estado = "vencida"
    _cambiar_estado_de_tiquetes(db, compra.id, "vencido")


def _total_pendiente(db: Session, compra: Transaccion) -> int:
    """Suma de los precios congelados de los tiquetes que todavía se deben cobrar."""
    total = db.scalar(
        select(func.coalesce(func.sum(Tramo.precio), 0))
        .join(Tiquete, Tiquete.tramo_id == Tramo.id)
        .where(
            Tramo.transaccion_id == compra.id,
            Tiquete.estado.in_(("bloqueado", "reservado")),
        )
    )
    return int(total or 0)


def _vuelos_de_transaccion(db: Session, transaccion_id: int) -> list[int]:
    return list(
        db.scalars(
            select(Tramo.vuelo_id)
            .where(Tramo.transaccion_id == transaccion_id)
            .distinct()
            .order_by(Tramo.vuelo_id)
        )
    )


def _enviar_correos_de_compra(db: Session, compra: Transaccion, momento: datetime) -> None:
    """Encola el código a cada viajero y el comprobante PDF al comprador (RF-39, HU-25)."""
    from app.modules.usuarios import service as usuarios_service

    codigo = compra.codigo or ""
    viaje = viaje_de(db, compra)
    for viajero in viaje.viajeros:
        encolar_correo(
            db,
            viajero.email,
            f"Tu compra {codigo} está confirmada",
            _texto_para_viajero(viaje, viajero, codigo),
        )

    comprador = usuarios_service.obtener_perfil(db, compra.cliente_id)
    datos = _datos_de_comprobante(viaje, comprador, momento)
    encolar_correo(
        db,
        comprador.email,
        f"Comprobante de compra {codigo}",
        f"Gracias por comprar con AVIANCO. Adjuntamos el comprobante de tu compra {codigo}.",
        adjuntos=[
            Adjunto(
                f"comprobante-{codigo}.pdf",
                "application/pdf",
                generar_comprobante(datos),
            )
        ],
    )


def _texto_para_viajero(viaje: Viaje, viajero: ViajeroViaje, codigo: str) -> str:
    """Texto del correo de confirmación, con el código, cada vuelo y su silla."""
    lineas = [
        f"Hola {viajero.nombres}, tu compra {codigo} está confirmada.",
        "",
    ]
    for tiquete in viajero.tiquetes:
        vuelo = viaje.tramos[tiquete.tramo].vuelo
        salida = _fecha_local(vuelo.salida, vuelo.origen.zona_horaria)
        lineas.append(
            f"Vuelo {vuelo.codigo}: {vuelo.origen.nombre} → {vuelo.destino.nombre}, "
            f"{salida} (hora local), clase {tiquete.clase}, silla {tiquete.silla}."
        )
    lineas += ["", "Presenta este código en el aeropuerto. ¡Buen viaje!"]
    return "\n".join(lineas)


def _datos_de_comprobante(viaje: Viaje, comprador: object, momento: datetime) -> DatosComprobante:
    """Adapta la respuesta pública del viaje a los datos del comprobante (HU-25)."""
    tramos = tuple(
        TramoComprobante(
            vuelo_codigo=tramo.vuelo.codigo,
            origen=tramo.vuelo.origen.nombre,
            destino=tramo.vuelo.destino.nombre,
            salida=tramo.vuelo.salida,
            zona_origen=tramo.vuelo.origen.zona_horaria,
            llegada=tramo.vuelo.llegada,
            zona_destino=tramo.vuelo.destino.zona_horaria,
        )
        for tramo in viaje.tramos
    )
    viajeros = tuple(
        ViajeroComprobante(
            nombres=viajero.nombres,
            apellidos=viajero.apellidos,
            tipo_documento=viajero.tipo_documento,
            numero_documento=viajero.numero_documento,
            tiquetes=tuple(
                TiqueteComprobante(
                    tramo=tiquete.tramo,
                    clase=tiquete.clase,
                    silla=tiquete.silla,
                    precio=tiquete.precio,
                )
                for tiquete in viajero.tiquetes
            ),
        )
        for viajero in viaje.viajeros
    )
    return DatosComprobante(
        codigo=viaje.codigo,
        comprador=f"{comprador.nombres} {comprador.apellidos}",
        pagado_en=momento,
        tramos=tramos,
        viajeros=viajeros,
        total=sum(tiquete.precio for viajero in viaje.viajeros for tiquete in viajero.tiquetes),
    )


def _fecha_local(momento: datetime, zona: str) -> str:
    """IU-05: fecha y hora en la zona del origen, en formato de 24 horas."""
    return f"{momento.astimezone(ZoneInfo(zona)):%d/%m/%Y %H:%M}"


def pasajeros_de_vuelo(db: Session, vuelo_id: int) -> list[PasajeroVuelo]:
    """Viajeros con tiquete comprado en el vuelo, con su clase y silla (HU-18).

    Solo incluye tiquetes `comprado`: una reserva o un bloqueo todavía no es un pasajero.
    """
    filas = db.execute(
        select(Viajero.nombres, Viajero.apellidos, Tramo.clase, Tiquete.numero_silla)
        .join(Tramo, Tiquete.tramo_id == Tramo.id)
        .join(Viajero, Tiquete.viajero_id == Viajero.id)
        .where(Tiquete.vuelo_id == vuelo_id, Tiquete.estado == "comprado")
        .order_by(Tiquete.numero_silla)
    ).all()
    return [
        PasajeroVuelo(
            nombres=nombres,
            apellidos=apellidos,
            clase=clase,
            numero_silla=numero_silla,
        )
        for nombres, apellidos, clase, numero_silla in filas
    ]


def tiquetes_activos_en_vuelo(db: Session, usuario_id: int, vuelo_id: int) -> int:
    """Tiquetes activos de un cliente en un vuelo (RF-32, HU-22).

    Es la cuenta que usa el carrito para el límite de 5; suma compras y reservas y excluye
    los tiquetes cancelados o vencidos.
    """
    return (
        db.scalar(
            select(func.count(Tiquete.id))
            .join(Tramo, Tiquete.tramo_id == Tramo.id)
            .join(Transaccion, Tramo.transaccion_id == Transaccion.id)
            .where(
                Transaccion.cliente_id == usuario_id,
                Tiquete.vuelo_id == vuelo_id,
                Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS),
            )
        )
        or 0
    )


def tiquetes_activos_futuros_de_cliente(db: Session, usuario_id: int) -> list[TiqueteActivo]:
    """Compras y reservas activas del cliente en vuelos que no han salido (HU-09).

    Devuelve una entrada por transacción y vuelo, no una por tiquete: para bloquear la
    desactivación de la cuenta basta saber que el cliente tiene un viaje pendiente.
    """
    # `vuelos.service` importa este módulo; se importa dentro de la función para no cerrar el
    # ciclo durante la carga inicial de `vuelos` (RF-18).
    from app.modules.vuelos import service as vuelos_service

    ahora = datetime.now(UTC)
    filas = db.execute(
        select(
            Tiquete.vuelo_id,
            Transaccion.id,
            Transaccion.tipo,
            Transaccion.codigo,
        )
        .join(Tramo, Tiquete.tramo_id == Tramo.id)
        .join(Transaccion, Tramo.transaccion_id == Transaccion.id)
        .where(
            Transaccion.cliente_id == usuario_id,
            Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS),
        )
        .order_by(Transaccion.id, Tiquete.vuelo_id)
    ).all()

    vistos: set[tuple[int, int]] = set()
    detalles: dict[int, vuelos_service.VueloDetalleGestion] = {}
    activos: list[TiqueteActivo] = []
    for vuelo_id, transaccion_id, tipo, codigo in filas:
        clave = (transaccion_id, vuelo_id)
        if clave in vistos:
            continue
        vistos.add(clave)

        detalle = detalles.get(vuelo_id)
        if detalle is None:
            detalle = vuelos_service.obtener_vuelo_detalle(db, vuelo_id)
            detalles[vuelo_id] = detalle
        if detalle.vuelo.salida <= ahora:
            continue

        activos.append(
            TiqueteActivo(
                tipo=tipo,
                codigo_reserva=codigo,
                vuelo_id=vuelo_id,
                vuelo_codigo=detalle.vuelo.codigo,
                origen=detalle.origen.nombre,
                destino=detalle.destino.nombre,
                salida=detalle.vuelo.salida,
            )
        )

    activos.sort(key=lambda tiquete: (tiquete.salida, tiquete.vuelo_id, tiquete.tipo))
    return activos


# ---------- Reglas de los viajeros (RF-31 a RF-35) ----------


def validar_viajeros(viajeros: Sequence[ViajeroParaValidar], *, hoy: date | None = None) -> None:
    """RF-31: rechaza campos obligatorios vacíos y correos con formato inválido.

    El error lleva la ruta de cada viajero (`viajeros.0.email`) para que el frontend marque
    el campo correcto. La fecha de nacimiento se valida con
    `usuarios.service.validar_fecha_nacimiento` y se reubica en el campo del viajero.
    """
    # Import diferido: usuarios.service importa este módulo al cargarse (ver docstring).
    from app.modules.usuarios import service as usuarios_service

    if not viajeros:
        raise DatosInvalidos(campos={"viajeros": "Debe incluir al menos un viajero."})

    fecha_de_hoy = hoy or _hoy_colombia()
    campos: dict[str, str] = {}
    obligatorios = (
        "tipo_documento",
        "numero_documento",
        "nombres",
        "apellidos",
        "telefono",
        "email",
        "contacto_nombre",
        "contacto_telefono",
    )

    for indice, viajero in enumerate(viajeros):
        for nombre_campo in obligatorios:
            valor = getattr(viajero, nombre_campo, None)
            if not isinstance(valor, str) or not valor.strip():
                campos[f"viajeros.{indice}.{nombre_campo}"] = "Este campo es obligatorio."

        if (
            isinstance(viajero.email, str)
            and viajero.email.strip()
            and _PATRON_EMAIL.fullmatch(viajero.email.strip()) is None
        ):
            campos[f"viajeros.{indice}.email"] = "El formato no es válido."

        if not isinstance(viajero.genero, str) or not viajero.genero.strip():
            campos[f"viajeros.{indice}.genero"] = "Este campo es obligatorio."
        elif viajero.genero not in _GENEROS:
            campos[f"viajeros.{indice}.genero"] = "No es una opción válida."

        fecha = viajero.fecha_nacimiento
        if not isinstance(fecha, date):
            campos[f"viajeros.{indice}.fecha_nacimiento"] = "Este campo es obligatorio."
            continue
        try:
            usuarios_service.validar_fecha_nacimiento(fecha, fecha_de_hoy)
        except DatosInvalidos as error:
            mensaje = (error.campos or {}).get("fecha_nacimiento", error.mensaje)
            campos[f"viajeros.{indice}.fecha_nacimiento"] = mensaje

    if campos:
        raise DatosInvalidos(campos=campos)


def validar_limite_de_tiquetes(db: Session, usuario_id: int, vuelo_id: int, cantidad: int) -> None:
    """RF-32: un cliente no puede superar 5 tiquetes activos en un vuelo.

    `cantidad` son los tiquetes nuevos que se quieren agregar. Un tiquete cancelado o
    vencido no cuenta, así que el cliente puede volver a comprar después de cancelar.
    """
    if cantidad <= 0:
        return
    activos = tiquetes_activos_en_vuelo(db, usuario_id, vuelo_id)
    if activos + cantidad > MAXIMO_TIQUETES_POR_VUELO:
        raise LimiteDeTiquetes()


def validar_cupo(db: Session, vuelo_id: int, clase: Clase, cantidad: int) -> None:
    """RF-33: valida la disponibilidad solo en la clase elegida.

    Si primera está agotada se rechaza aunque económica tenga sillas. `cantidad` es el total
    de viajeros nuevos de esa clase en el vuelo.
    """
    if cantidad <= 0:
        return
    from app.modules.vuelos import service as vuelos_service

    detalle = vuelos_service.obtener_vuelo_detalle(db, vuelo_id)
    disponibles = (
        detalle.primera.disponibles if clase == "primera" else detalle.economica.disponibles
    )
    if cantidad > disponibles:
        raise SillasInsuficientes()


def validar_documentos_en_vuelo(
    db: Session, vuelo_id: int, viajeros: Sequence[ViajeroParaValidar]
) -> None:
    """RF-34: ningún documento puede tener dos tiquetes activos en el mismo vuelo.

    Compara contra los tiquetes activos de todos los clientes y contra los documentos
    repetidos en la misma solicitud. El mensaje no revela quién hizo la otra compra.
    """
    if not viajeros:
        return

    documentos = [
        (
            indice,
            _normalizar_documento(viajero.tipo_documento),
            _normalizar_documento(viajero.numero_documento),
        )
        for indice, viajero in enumerate(viajeros)
    ]
    existentes = {
        (_normalizar_documento(tipo), _normalizar_documento(numero))
        for tipo, numero in db.execute(
            select(Tiquete.tipo_documento, Tiquete.numero_documento).where(
                Tiquete.vuelo_id == vuelo_id,
                Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS),
            )
        ).all()
    }

    vistos: set[tuple[str, str]] = set()
    campos: dict[str, str] = {}
    for indice, tipo, numero in documentos:
        if not tipo or not numero:
            # El campo vacío lo reporta `validar_viajeros` con su propia ruta.
            continue
        clave = (tipo, numero)
        if clave in existentes or clave in vistos:
            campos[f"viajeros.{indice}.numero_documento"] = (
                "Este documento ya tiene un tiquete activo en este vuelo."
            )
        vistos.add(clave)

    if campos:
        raise ViajeroDuplicado(campos=campos)


def validar_menores(db: Session, vuelo_id: int, viajeros: Sequence[ViajeroParaValidar]) -> None:
    """RF-35: un menor solo puede viajar si hay un adulto en el mismo vuelo.

    La edad se calcula a la fecha de salida en la hora local del origen, no a la fecha de la
    compra. Un viajero que cumple 18 años el día del vuelo ya es adulto.
    """
    if not viajeros:
        return
    from app.modules.vuelos import service as vuelos_service

    detalle = vuelos_service.obtener_vuelo_detalle(db, vuelo_id)
    fecha_salida = detalle.vuelo.salida.astimezone(ZoneInfo(detalle.origen.zona_horaria)).date()

    adultos = 0
    menores: list[int] = []
    for indice, viajero in enumerate(viajeros):
        fecha = viajero.fecha_nacimiento
        if not isinstance(fecha, date):
            # `validar_viajeros` ya reporta la fecha faltante.
            continue
        if _edad_en(fecha, fecha_salida) >= 18:
            adultos += 1
        else:
            menores.append(indice)

    if menores and adultos == 0:
        mensaje = "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo."
        raise MenorSinAdulto(
            campos={f"viajeros.{indice}.fecha_nacimiento": mensaje for indice in menores}
        )


def _hoy_colombia() -> date:
    """Fecha local de Colombia para validar la fecha de nacimiento (SUP-32, SUP-43)."""
    return datetime.now(UTC).astimezone(_ZONA_NEGOCIO).date()


def _edad_en(fecha_nacimiento: date, fecha: date) -> int:
    """Edad cumplida a `fecha`, con el cumpleaños como límite (RF-35)."""
    return (
        fecha.year
        - fecha_nacimiento.year
        - ((fecha.month, fecha.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    )


def _normalizar_documento(valor: str) -> str:
    """Normaliza tipo y número para comparar documentos sin distinguir mayúsculas."""
    return valor.strip().upper()


# ---------- Auxiliares de la reserva (HU-24) ----------


def _exigir_correo_verificado(db: Session, usuario_id: int) -> None:
    """HU-02: reservar o comprar exige el correo de la cuenta verificado."""
    from app.modules.usuarios import service as usuarios_service

    perfil = usuarios_service.obtener_perfil(db, usuario_id)
    if not perfil.email_verificado:
        raise usuarios_service.CorreoNoVerificado("Verifica tu correo para reservar o comprar.")


def _validar_clases(datos: ViajeEntrada) -> None:
    """RF-33: cada viajero trae una clase por tramo, en el orden de `tramos`."""
    campos = {
        f"viajeros.{indice}.clases": "Debe traer una clase por cada tramo."
        for indice, viajero in enumerate(datos.viajeros)
        if len(viajero.clases) != len(datos.tramos)
    }
    if campos:
        raise DatosInvalidos(campos=campos)


def _a_viajero_para_validar(viajero: object) -> ViajeroParaValidar:
    """Convierte el `ViajeroEntrada` de la API en la forma de entrada del service."""
    return ViajeroParaValidar(
        tipo_documento=viajero.tipo_documento,
        numero_documento=viajero.numero_documento,
        nombres=viajero.nombres,
        apellidos=viajero.apellidos,
        fecha_nacimiento=viajero.fecha_nacimiento,
        genero=viajero.genero,
        telefono=viajero.telefono,
        email=viajero.email,
        contacto_nombre=viajero.contacto_nombre,
        contacto_telefono=viajero.contacto_telefono,
    )


def _bloquear_vuelo(db: Session, vuelo_id: int) -> None:
    """Serializa las asignaciones del vuelo con un lock de asesoría (RF-42).

    No bloquea la fila de `vuelos`, que es de otro módulo: solo reserva y compra compiten
    entre sí por las sillas del mismo vuelo. El lock se libera al terminar la transacción.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(:clave, :vuelo_id)"),
        {"clave": _CLAVE_LOCK_VUELOS, "vuelo_id": vuelo_id},
    )


def _bloquear_y_validar_tramos(db: Session, datos: ViajeEntrada, momento: datetime) -> list:
    """Bloquea los vuelos en orden de id y valida que se vendan (HU-24)."""
    from app.modules.vuelos import service as vuelos_service

    # Los locks van en orden de id para que dos reservas con dos vuelos no se bloqueen entre sí.
    for vuelo_id in sorted({tramo.vuelo_id for tramo in datos.tramos}):
        _bloquear_vuelo(db, vuelo_id)

    detalles = []
    for indice, tramo in enumerate(datos.tramos):
        try:
            detalle = vuelos_service.obtener_vuelo_detalle(db, tramo.vuelo_id, ahora=momento)
        except NoEncontrado:
            raise _vuelo_no_disponible(indice) from None
        if detalle.vuelo.estado != "programado":
            raise _vuelo_no_disponible(indice)
        if momento >= vuelos_service.limite_de_venta(detalle.vuelo.tipo, detalle.vuelo.salida):
            raise _fuera_de_plazo(indice, detalle.vuelo)
        detalles.append(detalle)
    return detalles


def _vuelo_no_disponible(indice: int) -> VueloNoDisponible:
    return VueloNoDisponible(
        campos={f"tramos.{indice}.vuelo_id": "El vuelo no existe o ya no está programado."}
    )


def _fuera_de_plazo(indice: int, vuelo: object) -> FueraDePlazo:
    horas = 1 if vuelo.tipo == "nacional" else 3
    otras = 3 if horas == 1 else 1
    return FueraDePlazo(
        f"La venta de {vuelo.codigo} ya cerró: cierra {horas} "
        f"{'hora' if horas == 1 else 'horas'} antes de la salida ({otras} "
        f"{'hora' if otras == 1 else 'horas'} si es "
        f"{'internacional' if horas == 1 else 'nacional'}).",
        campos={f"tramos.{indice}.vuelo_id": "Ya no se puede reservar ni comprar."},
    )


def _validar_regreso(detalles: list) -> None:
    """RF-28: el regreso sale del destino de la ida, después de su llegada y es otro vuelo."""
    if len(detalles) != 2:
        return
    ida, regreso = detalles
    if (
        regreso.vuelo.id == ida.vuelo.id
        or regreso.vuelo.origen_codigo != ida.vuelo.destino_codigo
        or regreso.vuelo.salida < ida.vuelo.llegada
    ):
        raise RegresoInvalido(
            f"El regreso debe salir de {ida.destino.nombre} después de la llegada de la ida.",
            campos={"tramos.1.vuelo_id": "Elige un regreso que salga después de tu llegada."},
        )


def _insertar_transaccion(
    db: Session,
    usuario_id: int,
    datos: ViajeEntrada,
    detalles: list,
    momento: datetime,
    *,
    tipo: Literal["compra", "reserva"],
    estado: str,
    vence_en: datetime | None,
    bloqueo_hasta: datetime | None,
    estado_tiquete: EstadoTiquete,
) -> Transaccion:
    """Crea la transacción y reintenta la asignación si otra petición tomó las sillas (RF-42)."""
    for intento in range(_INTENTOS_DE_ASIGNACION):
        try:
            with db.begin_nested():
                transaccion = _crear_transaccion(
                    db,
                    usuario_id,
                    datos,
                    detalles,
                    momento,
                    tipo=tipo,
                    estado=estado,
                    vence_en=vence_en,
                    bloqueo_hasta=bloqueo_hasta,
                    estado_tiquete=estado_tiquete,
                )
            return transaccion
        except IntegrityError as error:
            restriccion = _restriccion_de(error)
            if restriccion == "uq_tiquetes_vuelo_documento_activo":
                # Otra petición tomó el documento: se vuelve a validar para llenar `campos`.
                viajeros = [_a_viajero_para_validar(viajero) for viajero in datos.viajeros]
                for detalle in detalles:
                    validar_documentos_en_vuelo(db, detalle.vuelo.id, viajeros)
                raise ViajeroDuplicado() from None
            if restriccion == "uq_transacciones_codigo":
                # Colisión de código (1 en mil millones): se genera otro en el siguiente intento.
                if intento == _INTENTOS_DE_ASIGNACION - 1:
                    raise
                continue
            if (
                restriccion != "uq_tiquetes_vuelo_silla_activa"
                or intento == _INTENTOS_DE_ASIGNACION - 1
            ):
                raise
    raise AssertionError("No se pudo crear el viaje.")


def _crear_transaccion(
    db: Session,
    usuario_id: int,
    datos: ViajeEntrada,
    detalles: list,
    momento: datetime,
    *,
    tipo: Literal["compra", "reserva"],
    estado: str,
    vence_en: datetime | None,
    bloqueo_hasta: datetime | None,
    estado_tiquete: EstadoTiquete,
) -> Transaccion:
    from app.modules.vuelos import service as vuelos_service

    transaccion = Transaccion(
        cliente_id=usuario_id,
        tipo=tipo,
        estado=estado,
        codigo=_nuevo_codigo(db),
        vence_en=vence_en,
        bloqueo_hasta=bloqueo_hasta,
    )
    db.add(transaccion)
    db.flush()

    tramos: dict[tuple[int, Clase], Tramo] = {}
    for indice, detalle in enumerate(detalles):
        for clase in ("primera", "economica"):
            if not any(viajero.clases[indice] == clase for viajero in datos.viajeros):
                continue
            tramo = Tramo(
                transaccion_id=transaccion.id,
                vuelo_id=detalle.vuelo.id,
                clase=clase,
                precio=vuelos_service.precio_vigente(
                    db, detalle.vuelo.id, clase, ahora=momento
                ).precio,
                orden=indice + 1,
            )
            db.add(tramo)
            db.flush()
            tramos[(indice, clase)] = tramo

    sillas: list[dict[int, int]] = [{} for _ in datos.viajeros]
    for indice, detalle in enumerate(detalles):
        for clase in ("primera", "economica"):
            indices = [
                i for i, viajero in enumerate(datos.viajeros) if viajero.clases[indice] == clase
            ]
            if not indices:
                continue
            ocupadas = set(
                db.scalars(
                    select(Tiquete.numero_silla).where(
                        Tiquete.vuelo_id == detalle.vuelo.id,
                        Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS),
                    )
                )
            )
            numeros = asignar_sillas(
                detalle.vuelo.tipo, clase, ocupadas, len(indices), random.SystemRandom()
            )
            for posicion, numero in zip(indices, numeros, strict=True):
                sillas[posicion][indice] = numero

    for posicion, datos_viajero in enumerate(datos.viajeros):
        viajero = Viajero(
            transaccion_id=transaccion.id,
            tipo_documento=datos_viajero.tipo_documento,
            numero_documento=datos_viajero.numero_documento,
            nombres=datos_viajero.nombres,
            apellidos=datos_viajero.apellidos,
            fecha_nacimiento=datos_viajero.fecha_nacimiento,
            genero=datos_viajero.genero,
            telefono=datos_viajero.telefono,
            email=datos_viajero.email,
            contacto_nombre=datos_viajero.contacto_nombre,
            contacto_telefono=datos_viajero.contacto_telefono,
        )
        db.add(viajero)
        db.flush()
        for indice in range(len(detalles)):
            clase = datos_viajero.clases[indice]
            tramo = tramos[(indice, clase)]
            db.add(
                Tiquete(
                    tramo_id=tramo.id,
                    viajero_id=viajero.id,
                    vuelo_id=tramo.vuelo_id,
                    numero_silla=sillas[posicion][indice],
                    estado=estado_tiquete,
                    tipo_documento=viajero.tipo_documento,
                    numero_documento=viajero.numero_documento,
                )
            )
    db.flush()
    return transaccion


def _nuevo_codigo(db: Session) -> str:
    """RF-39: código alfanumérico único de 6 caracteres; se genera al reservar o comprar."""
    while True:
        codigo = "".join(secrets.choice(_CODIGO_ALFABETO) for _ in range(_CODIGO_LARGO))
        if db.scalar(select(Transaccion.id).where(Transaccion.codigo == codigo)) is None:
            return codigo


def _restriccion_de(error: IntegrityError) -> str:
    """Nombre de la restricción que falló, para distinguir una silla de un documento."""
    origen = getattr(error, "orig", None)
    diagnostico = getattr(origen, "diag", None)
    return getattr(diagnostico, "constraint_name", None) or ""


def _cambiar_estado_de_tiquetes(db: Session, transaccion_id: int, estado: EstadoTiquete) -> None:
    """Pasa todos los tiquetes de la transacción a `estado` (libera sillas o documentos)."""
    tramos = select(Tramo.id).where(Tramo.transaccion_id == transaccion_id)
    db.execute(update(Tiquete).where(Tiquete.tramo_id.in_(tramos)).values(estado=estado))


def _encolar_aviso(db: Session, transaccion: Transaccion, asunto: str, texto: str) -> None:
    """Encola un correo al cliente de la transacción, si la cuenta todavía existe."""
    correo = _correo_del_cliente(db, transaccion.cliente_id)
    if correo is not None:
        encolar_correo(db, correo, asunto, texto)


def _correo_del_cliente(db: Session, cliente_id: int) -> str | None:
    from app.modules.usuarios import service as usuarios_service

    try:
        return usuarios_service.obtener_perfil(db, cliente_id).email
    except (NoAutenticado, NoEncontrado):
        return None


def _vuelo_viaje(detalle: object) -> VueloViaje:
    """Forma pública del vuelo dentro de una reserva o compra."""
    vuelo = detalle.vuelo
    return VueloViaje(
        id=vuelo.id,
        codigo=vuelo.codigo,
        tipo=vuelo.tipo,
        origen=CiudadViaje(
            codigo=detalle.origen.codigo,
            nombre=detalle.origen.nombre,
            zona_horaria=detalle.origen.zona_horaria,
        ),
        destino=CiudadViaje(
            codigo=detalle.destino.codigo,
            nombre=detalle.destino.nombre,
            zona_horaria=detalle.destino.zona_horaria,
        ),
        salida=vuelo.salida,
        llegada=vuelo.llegada,
        duracion_minutos=vuelo.duracion_minutos,
        estado=vuelo.estado,
    )


# RF-37, RNF-18: el planificador vence las reservas cada minuto, también al arrancar.
registrar_tarea(NOMBRE_TAREA_VENCER, vencer_reservas, cada=timedelta(minutes=1))

# SUP-15, RNF-18: libera los bloqueos de las compras cada minuto, también al arrancar.
registrar_tarea(NOMBRE_TAREA_LIBERAR, liberar_bloqueos, cada=timedelta(minutes=1))
