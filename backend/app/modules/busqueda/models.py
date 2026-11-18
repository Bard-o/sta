"""Modelo de las búsquedas registradas para la recomendación (RF-29, RF-60, SUP-34)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Busqueda(Base):
    """Búsqueda de un cliente autenticado. No se edita ni se borra."""

    __tablename__ = "busquedas"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Una llave foránea hacia otro módulo se declara con el nombre de su tabla (AGENTS.md).
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    # Criterios tal como llegaron (sin valores vacíos) más `orden`: la recomendación los lee
    # en la iteración 4 (RF-60). JSONB para no migrar por cada atributo que necesite.
    criterios: Mapped[dict[str, Any]] = mapped_column(JSONB)
    total: Mapped[int] = mapped_column(Integer)
    registrada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
