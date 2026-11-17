"""Modelos del módulo reservas (RF-31 a RF-35, RF-39 a RF-42, SUP-09 a SUP-15).

Una `Transaccion` es una reserva o una compra del cliente. Cada `Tramo` congela el vuelo, la
clase y el precio; los `Viajero` de la transacción se vinculan a cada tramo mediante un
`Tiquete`, que guarda la silla asignada y su estado.

Las sillas y los documentos se protegen con índices únicos parciales: solo compiten los
tiquetes activos (`bloqueado`, `reservado`, `comprado`). Así la base de datos hace cumplir
RF-34 y RF-42 aunque dos peticiones lleguen al mismo tiempo, y un tiquete cancelado o vencido
libera su silla y su documento.
"""

from datetime import date, datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

TipoTransaccion = Literal["reserva", "compra"]
EstadoTransaccion = Literal[
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
    "bloqueado",
    "reservado",
    "comprado",
    "cancelado",
    "vencido",
    "reembolsado",
    "reubicado",
]
Clase = Literal["economica", "primera"]
Genero = Literal["femenino", "masculino", "otro"]

# RF-32, RF-34, RF-42: solo estos estados ocupan silla y documento. Un tiquete cancelado,
# vencido, reembolsado o reubicado ya no cuenta.
ESTADOS_TIQUETE_ACTIVOS: tuple[EstadoTiquete, ...] = ("bloqueado", "reservado", "comprado")
_ACTIVOS_SQL = "estado IN ('bloqueado', 'reservado', 'comprado')"


class Transaccion(TimestampMixin, Base):
    """Reserva o compra de un cliente (HU-24, HU-25, HU-26).

    `vence_en` es el vencimiento de la reserva (RF-36). `bloqueo_hasta` es la ventana corta
    de la compra mientras se confirma el pago (SUP-15). Son campos distintos: una reserva
    puede durar 24 horas y un bloqueo de pago, 15 minutos.
    """

    __tablename__ = "transacciones"
    __table_args__ = (
        CheckConstraint("codigo IS NULL OR length(codigo) = 6", name="codigo_de_seis_caracteres"),
        CheckConstraint(
            "tipo <> 'reserva' OR vence_en IS NOT NULL", name="reserva_con_vencimiento"
        ),
        Index("ix_transacciones_cliente_estado", "cliente_id", "estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[TipoTransaccion] = mapped_column(
        Enum(
            "reserva",
            "compra",
            name="tipo_transaccion",
            native_enum=False,
            length=7,
            create_constraint=True,
        )
    )
    estado: Mapped[EstadoTransaccion] = mapped_column(
        Enum(
            "pendiente",
            "vigente",
            "pagada",
            "vencida",
            "activa",
            "cancelada",
            "realizada",
            "reembolsada",
            "reubicada",
            name="estado_transaccion",
            native_enum=False,
            length=11,
            create_constraint=True,
        )
    )
    # RF-39: código alfanumérico único de 6 caracteres; se genera al confirmar la compra.
    codigo: Mapped[str | None] = mapped_column(String(6), unique=True)
    # RF-36: vencimiento de la reserva (24 horas o el límite de cancelación del vuelo).
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # SUP-15: la compra bloquea las sillas 15 minutos mientras se confirma el pago.
    bloqueo_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Tramo(Base):
    """Vuelo, clase y precio congelado de una transacción (RF-33, RF-40).

    Una transacción de ida y regreso tiene dos `orden` (1 y 2). Si en un mismo vuelo hay
    viajeros en clases distintas, hay un tramo por clase; el viajero queda en la clase del
    tramo de su tiquete. `precio` no se recalcula: conserva el valor vigente al reservar o
    comprar (RF-24).
    """

    __tablename__ = "tramos"
    __table_args__ = (
        CheckConstraint("orden BETWEEN 1 AND 2", name="orden_valido"),
        CheckConstraint("precio > 0", name="precio_positivo"),
        UniqueConstraint(
            "transaccion_id", "orden", "clase", name="uq_tramos_transaccion_orden_clase"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaccion_id: Mapped[int] = mapped_column(
        ForeignKey("transacciones.id", ondelete="CASCADE"), index=True
    )
    vuelo_id: Mapped[int] = mapped_column(ForeignKey("vuelos.id"), index=True)
    clase: Mapped[Clase] = mapped_column(
        Enum(
            "economica",
            "primera",
            name="clase_tramo",
            native_enum=False,
            length=9,
            create_constraint=True,
        )
    )
    precio: Mapped[int] = mapped_column(Integer)
    orden: Mapped[int] = mapped_column(Integer)


class Viajero(TimestampMixin, Base):
    """Datos de un viajero de la transacción (RF-31).

    El mismo viajero puede viajar en varios tramos de la transacción. No puede repetirse
    dentro de una misma transacción (tipo y número de documento).
    """

    __tablename__ = "viajeros"
    __table_args__ = (
        UniqueConstraint(
            "transaccion_id",
            "tipo_documento",
            "numero_documento",
            name="uq_viajeros_transaccion_documento",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaccion_id: Mapped[int] = mapped_column(
        ForeignKey("transacciones.id", ondelete="CASCADE"), index=True
    )
    tipo_documento: Mapped[str] = mapped_column(String(2))
    numero_documento: Mapped[str] = mapped_column(String(20))
    nombres: Mapped[str] = mapped_column(String(100))
    apellidos: Mapped[str] = mapped_column(String(100))
    fecha_nacimiento: Mapped[date] = mapped_column(Date)
    genero: Mapped[Genero] = mapped_column(
        Enum(
            "femenino",
            "masculino",
            "otro",
            name="genero_viajero",
            native_enum=False,
            length=9,
            create_constraint=True,
        )
    )
    telefono: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(254))
    contacto_nombre: Mapped[str] = mapped_column(String(100))
    contacto_telefono: Mapped[str] = mapped_column(String(20))


class Tiquete(TimestampMixin, Base):
    """Tiquete de un viajero en un tramo, con su silla (RF-33, RF-34, RF-41, RF-42).

    `vuelo_id`, `tipo_documento` y `numero_documento` se repiten desde el tramo y el viajero
    para que PostgreSQL pueda imponer los índices únicos parciales sin subconsultas: una
    silla activa por vuelo y un documento activo por vuelo (RF-34, RF-42).
    """

    __tablename__ = "tiquetes"
    __table_args__ = (
        CheckConstraint("numero_silla > 0", name="silla_positiva"),
        UniqueConstraint("tramo_id", "viajero_id", name="uq_tiquetes_tramo_viajero"),
        Index("ix_tiquetes_vuelo_estado", "vuelo_id", "estado"),
        Index(
            "uq_tiquetes_vuelo_silla_activa",
            "vuelo_id",
            "numero_silla",
            unique=True,
            postgresql_where=text(_ACTIVOS_SQL),
        ),
        Index(
            "uq_tiquetes_vuelo_documento_activo",
            "vuelo_id",
            "tipo_documento",
            "numero_documento",
            unique=True,
            postgresql_where=text(_ACTIVOS_SQL),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tramo_id: Mapped[int] = mapped_column(ForeignKey("tramos.id", ondelete="CASCADE"), index=True)
    viajero_id: Mapped[int] = mapped_column(
        ForeignKey("viajeros.id", ondelete="CASCADE"), index=True
    )
    vuelo_id: Mapped[int] = mapped_column(ForeignKey("vuelos.id"), index=True)
    numero_silla: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoTiquete] = mapped_column(
        Enum(
            "bloqueado",
            "reservado",
            "comprado",
            "cancelado",
            "vencido",
            "reembolsado",
            "reubicado",
            name="estado_tiquete",
            native_enum=False,
            length=11,
            create_constraint=True,
        )
    )
    # Copia del documento del viajero, necesaria para el índice único parcial de RF-34.
    tipo_documento: Mapped[str] = mapped_column(String(2))
    numero_documento: Mapped[str] = mapped_column(String(20))
