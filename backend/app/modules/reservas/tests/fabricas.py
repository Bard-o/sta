"""Fábricas de reservas, compras, viajeros y tiquetes para los tests.

Reutiliza `vuelos.tests.fabricas.crear_vuelo` para el vuelo. Las usan los tests de este
módulo y los de #118 a #131 para preparar estados sin pasar por los endpoints.
"""

from datetime import UTC, date, datetime, timedelta
from itertools import count
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.reservas.models import (
    ESTADOS_TIQUETE_ACTIVOS,
    Clase,
    EstadoTiquete,
    EstadoTransaccion,
    Tiquete,
    Tramo,
    Transaccion,
    Viajero,
)
from app.modules.reservas.service import ViajeroParaValidar
from app.modules.vuelos.models import Vuelo

_DOCUMENTOS = count(1)


def crear_transaccion(
    db: Session,
    cliente_id: int,
    *,
    tipo: str = "reserva",
    estado: EstadoTransaccion | None = None,
    codigo: str | None = None,
    vence_en: datetime | None = None,
    bloqueo_hasta: datetime | None = None,
) -> Transaccion:
    """Crea una Reserva o compra del cliente; por defecto una reserva vigente de 24 horas."""
    if estado is None:
        estado = "vigente" if tipo == "reserva" else "pagada"
    if tipo == "reserva" and vence_en is None:
        vence_en = datetime.now(UTC) + timedelta(hours=24)

    transaccion = Transaccion(
        cliente_id=cliente_id,
        tipo=tipo,
        estado=estado,
        codigo=codigo,
        vence_en=vence_en,
        bloqueo_hasta=bloqueo_hasta,
    )
    db.add(transaccion)
    db.flush()
    return transaccion


def crear_tramo(
    db: Session,
    transaccion: Transaccion,
    vuelo: Vuelo,
    *,
    clase: Clase = "economica",
    precio: int | None = None,
    orden: int = 1,
) -> Tramo:
    """Crea el tramo de un vuelo y congela el precio de la clase indicada."""
    if precio is None:
        precio = vuelo.precio_primera if clase == "primera" else vuelo.precio_economica
    tramo = Tramo(
        transaccion_id=transaccion.id,
        vuelo_id=vuelo.id,
        clase=clase,
        precio=precio,
        orden=orden,
    )
    db.add(tramo)
    db.flush()
    return tramo


def crear_viajero(
    db: Session,
    transaccion: Transaccion,
    *,
    tipo_documento: str = "CC",
    numero_documento: str | None = None,
    nombres: str = "Ana",
    apellidos: str = "Pérez",
    fecha_nacimiento: date = date(1990, 1, 1),
    genero: str = "femenino",
    telefono: str = "3001234567",
    email: str | None = None,
    contacto_nombre: str = "Carlos Pérez",
    contacto_telefono: str = "3007654321",
) -> Viajero:
    """Crea un viajero con datos válidos; el documento y el correo se generan si faltan."""
    if numero_documento is None:
        numero_documento = f"9{next(_DOCUMENTOS):09d}"
    if email is None:
        email = f"viajero{numero_documento}@example.com"

    viajero = Viajero(
        transaccion_id=transaccion.id,
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
        nombres=nombres,
        apellidos=apellidos,
        fecha_nacimiento=fecha_nacimiento,
        genero=genero,
        telefono=telefono,
        email=email,
        contacto_nombre=contacto_nombre,
        contacto_telefono=contacto_telefono,
    )
    db.add(viajero)
    db.flush()
    return viajero


def crear_tiquete(
    db: Session,
    tramo: Tramo,
    viajero: Viajero,
    *,
    vuelo: Vuelo,
    estado: EstadoTiquete = "comprado",
    numero_silla: int | None = None,
) -> Tiquete:
    """Crea el tiquete y, si no se indica, le asigna la primera silla libre de la clase."""
    if numero_silla is None:
        numero_silla = _primera_silla_libre(db, vuelo, tramo.clase)

    tiquete = Tiquete(
        tramo_id=tramo.id,
        viajero_id=viajero.id,
        vuelo_id=vuelo.id,
        numero_silla=numero_silla,
        estado=estado,
        tipo_documento=viajero.tipo_documento,
        numero_documento=viajero.numero_documento,
    )
    db.add(tiquete)
    db.flush()
    return tiquete


def crear_reserva(
    db: Session,
    cliente_id: int,
    vuelo: Vuelo,
    *,
    clase: Clase = "economica",
    cantidad: int = 1,
    estado: EstadoTransaccion = "vigente",
    vence_en: datetime | None = None,
    estado_tiquete: EstadoTiquete = "reservado",
    **datos_viajero: Any,
) -> Transaccion:
    """Reserva de `cantidad` viajeros en un vuelo, con sus sillas asignadas."""
    transaccion = crear_transaccion(
        db, cliente_id, tipo="reserva", estado=estado, vence_en=vence_en
    )
    tramo = crear_tramo(db, transaccion, vuelo, clase=clase)
    for _ in range(cantidad):
        viajero = crear_viajero(db, transaccion, **datos_viajero)
        crear_tiquete(db, tramo, viajero, vuelo=vuelo, estado=estado_tiquete)
    return transaccion


def crear_compra(
    db: Session,
    cliente_id: int,
    vuelo: Vuelo,
    *,
    clase: Clase = "economica",
    cantidad: int = 1,
    estado: EstadoTransaccion = "pagada",
    codigo: str | None = None,
    bloqueo_hasta: datetime | None = None,
    estado_tiquete: EstadoTiquete = "comprado",
    **datos_viajero: Any,
) -> Transaccion:
    """Compra de `cantidad` viajeros en un vuelo, con sus sillas asignadas."""
    transaccion = crear_transaccion(
        db,
        cliente_id,
        tipo="compra",
        estado=estado,
        codigo=codigo,
        bloqueo_hasta=bloqueo_hasta,
    )
    tramo = crear_tramo(db, transaccion, vuelo, clase=clase)
    for _ in range(cantidad):
        viajero = crear_viajero(db, transaccion, **datos_viajero)
        crear_tiquete(db, tramo, viajero, vuelo=vuelo, estado=estado_tiquete)
    return transaccion


def datos_viajero(**cambios: Any) -> ViajeroParaValidar:
    """Viajero válido para probar las reglas de RF-31 a RF-35."""
    base: dict[str, Any] = {
        "tipo_documento": "CC",
        "numero_documento": "1020304050",
        "nombres": "Ana",
        "apellidos": "Pérez",
        "fecha_nacimiento": date(1990, 1, 1),
        "genero": "femenino",
        "telefono": "3001234567",
        "email": "ana@example.com",
        "contacto_nombre": "Carlos Pérez",
        "contacto_telefono": "3007654321",
    }
    base.update(cambios)
    return ViajeroParaValidar(**base)


def _primera_silla_libre(db: Session, vuelo: Vuelo, clase: Clase) -> int:
    """Primer número interno libre de la clase, según la capacidad del vuelo."""
    if clase == "primera":
        inicio, fin = 1, vuelo.capacidad_primera
    else:
        inicio = vuelo.capacidad_primera + 1
        fin = vuelo.capacidad_primera + vuelo.capacidad_economica
    ocupadas = set(
        db.scalars(
            select(Tiquete.numero_silla).where(
                Tiquete.vuelo_id == vuelo.id,
                Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS),
            )
        )
    )
    for numero in range(inicio, fin + 1):
        if numero not in ocupadas:
            return numero
    raise AssertionError("No hay sillas libres en la clase.")
