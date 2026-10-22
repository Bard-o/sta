"""Modelo del registro de auditoría (RF-26, RNF-16)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RegistroAuditoria(Base):
    """Acción administrativa registrada. No se edita ni se borra."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Una llave foránea hacia otro módulo se declara con el nombre de su tabla (AGENTS.md).
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    accion: Mapped[str] = mapped_column(String(40))
    entidad: Mapped[str] = mapped_column(String(20))
    entidad_id: Mapped[int] = mapped_column(Integer)
    antes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    despues: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
