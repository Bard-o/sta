"""Modelos del módulo vuelos (RF-12 a RF-16).

`ciudades` es el catálogo precargado por la migración. `vuelos` guarda la salida y la llegada
en UTC; la hora local se calcula con la zona IANA de cada ciudad. El código sale de una
secuencia de PostgreSQL y nunca se reutiliza (SUP-01).
"""

from datetime import datetime
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
