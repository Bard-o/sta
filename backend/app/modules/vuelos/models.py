"""Modelos del módulo vuelos (RF-12 a RF-16, RF-23).

`ciudades` es el catálogo precargado por la migración. `vuelos` guarda la salida y la llegada
en UTC; la hora local se calcula con la zona IANA de cada ciudad. El código sale de una
secuencia de PostgreSQL y nunca se reutiliza (SUP-01). `promociones` guarda el descuento por
clase y su vigencia; el estado efectivo se calcula al consultar (RF-23).
"""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

TipoCiudad = Literal["nacional", "internacional"]
TipoVuelo = Literal["nacional", "internacional"]
EstadoVuelo = Literal["programado", "realizado", "cancelado"]
Clase = Literal["economica", "primera"]
EstadoPromocion = Literal["programada", "vigente", "vencida", "agotada", "cancelada"]

SECUENCIA_CODIGO = "vuelos_codigo_seq"
_CODIGO_POR_DEFECTO = f"'STA-' || lpad(nextval('{SECUENCIA_CODIGO}')::text, 5, '0')"


class Ciudad(Base):
    __tablename__ = "ciudades"

    codigo: Mapped[str] = mapped_column(String(3), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    pais: Mapped[str] = mapped_column(String(100))
    zona_horaria: Mapped[str] = mapped_column(String(50))
    tipo: Mapped[TipoCiudad] = mapped_column(
        Enum(
            "nacional",
            "internacional",
            name="tipo_ciudad",
            native_enum=False,
            length=13,
            create_constraint=True,
        )
    )
    # RF-14: solo cinco ciudades colombianas tienen rutas internacionales.
    habilitada_internacional: Mapped[bool] = mapped_column(Boolean, server_default=false())
    imagen_url: Mapped[str] = mapped_column(String(255))


class Vuelo(TimestampMixin, Base):
    __tablename__ = "vuelos"
    __table_args__ = (
        CheckConstraint("origen_codigo <> destino_codigo", name="ruta_distinta"),
        CheckConstraint("duracion_minutos BETWEEN 1 AND 1439", name="duracion_valida"),
        CheckConstraint("precio_economica > 0 AND precio_primera > 0", name="precios_positivos"),
        CheckConstraint(
            "capacidad_primera > 0 AND capacidad_economica > 0",
            name="capacidades_positivas",
        ),
        CheckConstraint("llegada > salida", name="llegada_posterior"),
        # RF-16: solo un vuelo programado por ruta y salida. Los cancelados no bloquean.
        Index(
            "uq_vuelos_ruta_salida_programado",
            "origen_codigo",
            "destino_codigo",
            "salida",
            unique=True,
            postgresql_where=text("estado = 'programado'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # SUP-01: la secuencia es global y no se reutiliza, ni siquiera al cancelar el vuelo.
    codigo: Mapped[str] = mapped_column(
        String(9), unique=True, server_default=text(_CODIGO_POR_DEFECTO)
    )
    tipo: Mapped[TipoVuelo] = mapped_column(
        Enum(
            "nacional",
            "internacional",
            name="tipo_vuelo",
            native_enum=False,
            length=13,
            create_constraint=True,
        )
    )
    origen_codigo: Mapped[str] = mapped_column(ForeignKey("ciudades.codigo"))
    destino_codigo: Mapped[str] = mapped_column(ForeignKey("ciudades.codigo"))
    salida: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    llegada: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duracion_minutos: Mapped[int] = mapped_column(Integer)
    precio_economica: Mapped[int] = mapped_column(Integer)
    precio_primera: Mapped[int] = mapped_column(Integer)
    capacidad_primera: Mapped[int] = mapped_column(Integer)
    capacidad_economica: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoVuelo] = mapped_column(
        Enum(
            "programado",
            "realizado",
            "cancelado",
            name="estado_vuelo",
            native_enum=False,
            length=10,
            create_constraint=True,
        ),
        server_default=text("'programado'"),
    )


class Promocion(Base):
    """Promoción de una clase o de ambas en un vuelo (HU-17, RF-23).

    `estado` guarda `programada` mientras la promoción está activa o por empezar, y los
    estados terminales (`vencida`, `agotada`, `cancelada`). `vigente` y `vencida` por fecha
    se calculan al consultar con la hora inyectada, como en noticias (RF-23, RF-25).

    Los índices únicos parciales impiden acumular dos promociones activas en la misma clase.
    """

    __tablename__ = "promociones"
    __table_args__ = (
        CheckConstraint("porcentaje BETWEEN 1 AND 90", name="porcentaje_valido"),
        CheckConstraint("fin > inicio", name="vigencia_valida"),
        CheckConstraint("aplica_economica OR aplica_primera", name="aplica_alguna_clase"),
        Index(
            "uq_promociones_economica_activa",
            "vuelo_id",
            unique=True,
            postgresql_where=text("aplica_economica AND estado = 'programada'"),
        ),
        Index(
            "uq_promociones_primera_activa",
            "vuelo_id",
            unique=True,
            postgresql_where=text("aplica_primera AND estado = 'programada'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vuelo_id: Mapped[int] = mapped_column(ForeignKey("vuelos.id"), index=True)
    porcentaje: Mapped[int] = mapped_column(Integer)
    aplica_economica: Mapped[bool] = mapped_column(Boolean, server_default=false())
    aplica_primera: Mapped[bool] = mapped_column(Boolean, server_default=false())
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[EstadoPromocion] = mapped_column(
        Enum(
            "programada",
            "vigente",
            "vencida",
            "agotada",
            "cancelada",
            name="estado_promocion",
            native_enum=False,
            length=10,
            create_constraint=True,
        ),
        server_default=text("'programada'"),
    )
    # Se calcula en la aplicación para poder inyectar la hora en los tests (HU-17).
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
