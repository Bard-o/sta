"""Modelos del módulo noticias (RF-22, RF-25, RF-55).

Las noticias son automáticas y guardan una copia de los datos que muestran. No hay llaves
foráneas hacia vuelos por dos razones: noticias no consulta sus tablas (vuelos le avisa de
cada cambio) y la copia conserva lo que se publicó aunque el vuelo cambie después.

`vigente` es solo el retiro explícito. La vigencia efectiva se calcula al consultar: un vuelo
sigue vigente mientras no se retire y una promoción, además, mientras `promocion_fin` no haya
pasado (RF-25).
"""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

TipoNoticia = Literal["vuelo", "promocion"]
EstadoPromocionNoticia = Literal["programada", "vigente", "vencida", "agotada", "cancelada"]


class Noticia(Base):
    __tablename__ = "noticias"
    __table_args__ = (
        # Una noticia de vuelo no lleva datos de promoción.
        CheckConstraint(
            "tipo <> 'vuelo' OR ("
            "promocion_id IS NULL AND promocion_porcentaje IS NULL "
            "AND promocion_aplica_economica IS NULL AND promocion_aplica_primera IS NULL "
            "AND promocion_inicio IS NULL AND promocion_fin IS NULL "
            "AND promocion_estado IS NULL)",
            name="vuelo_sin_promocion",
        ),
        # Una noticia de promoción lleva todos sus datos y al menos una clase (RF-23).
        CheckConstraint(
            "tipo <> 'promocion' OR ("
            "promocion_id IS NOT NULL AND promocion_porcentaje IS NOT NULL "
            "AND promocion_aplica_economica IS NOT NULL "
            "AND promocion_aplica_primera IS NOT NULL "
            "AND promocion_inicio IS NOT NULL AND promocion_fin IS NOT NULL "
            "AND promocion_estado IS NOT NULL "
            "AND (promocion_aplica_economica OR promocion_aplica_primera) "
            "AND promocion_porcentaje BETWEEN 1 AND 90 "
            "AND promocion_fin > promocion_inicio)",
            name="promocion_completa",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoNoticia] = mapped_column(
        Enum(
            "vuelo",
            "promocion",
            name="tipo_noticia",
            native_enum=False,
            length=10,
            create_constraint=True,
        )
    )
    titulo: Mapped[str] = mapped_column(String(255))
    # Se calcula en la aplicación: `now()` en PostgreSQL es la hora de inicio de la
    # transacción y empataría todas las noticias publicadas en una misma serie (HU-14).
    publicada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # Retiro explícito (vuelo cancelado o realizado, promoción agotada o cancelada).
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    # Copia del vuelo. Sin ForeignKey: noticias no consulta la tabla de vuelos.
    vuelo_id: Mapped[int] = mapped_column(Integer, index=True)
    vuelo_codigo: Mapped[str] = mapped_column(String(20))
    origen_codigo: Mapped[str] = mapped_column(String(3))
    origen_nombre: Mapped[str] = mapped_column(String(100))
    origen_zona_horaria: Mapped[str] = mapped_column(String(50))
    destino_codigo: Mapped[str] = mapped_column(String(3))
    destino_nombre: Mapped[str] = mapped_column(String(100))
    destino_zona_horaria: Mapped[str] = mapped_column(String(50))
    salida: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    precio_economica: Mapped[int] = mapped_column(Integer)
    precio_primera: Mapped[int] = mapped_column(Integer)
    imagen_url: Mapped[str] = mapped_column(String(255))

    # Datos de la promoción; NULL en las noticias de vuelo.
    promocion_id: Mapped[int | None] = mapped_column(Integer, index=True)
    promocion_porcentaje: Mapped[int | None] = mapped_column(Integer)
    promocion_aplica_economica: Mapped[bool | None] = mapped_column(Boolean)
    promocion_aplica_primera: Mapped[bool | None] = mapped_column(Boolean)
    promocion_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promocion_fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Estado guardado: `programada` al publicar y terminal cuando se termina antes de `fin`.
    # `vigente` y `vencida` se derivan de las fechas al consultar.
    promocion_estado: Mapped[EstadoPromocionNoticia | None] = mapped_column(
        Enum(
            "programada",
            "vigente",
            "vencida",
            "agotada",
            "cancelada",
            name="estado_promocion_noticia",
            native_enum=False,
            length=12,
            create_constraint=True,
        )
    )
