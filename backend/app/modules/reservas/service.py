"""Interfaz pública del módulo reservas. Otros módulos solo llaman a estas funciones.

Aquí viven las reglas de los viajeros (RF-31 a RF-35) y las consultas que usan vuelos,
usuarios y carrito. Las funciones de escritura de la reserva, la compra y el vencimiento
llegan con las HU de la iteración 2 (#118, #124 y #130); esta entrega deja el modelo y las
reglas que esas historias reutilizan.

Ninguna función hace commit: van en la transacción de quien llama.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, DatosInvalidos
from app.modules.reservas.models import (
    ESTADOS_TIQUETE_ACTIVOS,
    Clase,
    Tiquete,
    Tramo,
    Transaccion,
    Viajero,
)
from app.modules.reservas.sillas import SillasInsuficientes
from app.modules.usuarios import service as usuarios_service

# RF-32: máximo de tiquetes activos de un cliente en un mismo vuelo, sumando clases.
MAXIMO_TIQUETES_POR_VUELO = 5

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
            .filter(Transaccion.tipo == "reserva", Transaccion.estado == "vigente")
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
    """Anula las reservas vigentes del vuelo, libera sus sillas y encola el correo a cada
    cliente (HU-16). Devuelve cuántas anuló. No hace commit.

    La implementación completa llega con #118; hasta entonces no hay reservas que anular.
    """
    return 0


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
