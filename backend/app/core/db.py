"""Motor y sesión de SQLAlchemy (síncrono)."""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

# Nombres de restricciones estables para que Alembic genere migraciones reproducibles.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Columnas de creación y actualización en UTC."""

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CorreoEnCola(TimestampMixin, Base):
    """Correo saliente pendiente de enviar (RNF-05, RNF-21; issue #5).

    Vive en core porque `alembic/env.py` solo descubre los modelos de los módulos y los que importa
    este archivo. Se escribe con `app.core.mail.encolar_correo`. Sus adjuntos están en
    `AdjuntoEnCola` (issue #116).
    """

    __tablename__ = "cola_correos"
    __table_args__ = (
        Index("ix_cola_correos_estado_proximo_intento_en", "estado", "proximo_intento_en"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    destinatario: Mapped[str] = mapped_column(String(254))
    asunto: Mapped[str] = mapped_column(String(255))
    texto: Mapped[str] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(
        Enum(
            "pendiente",
            "enviado",
            "fallido",
            name="estado_correo",
            native_enum=False,
            length=9,
            create_constraint=True,
        )
    )
    intentos: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    proximo_intento_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_error: Mapped[str | None] = mapped_column(Text)


class AdjuntoEnCola(Base):
    """Archivo adjunto de un correo de la cola (RF-39; issue #116).

    El contenido vive en `app.core.archivos` bajo `clave`; la cola guarda solo la referencia.
    `posicion` conserva el orden de los adjuntos y `tamano` (bytes) se comprueba al enviar.
    Lo escribe `app.core.mail.encolar_correo`; tras un envío exitoso se borra el archivo y la
    fila queda como registro.
    """

    __tablename__ = "cola_correos_adjuntos"
    __table_args__ = (
        UniqueConstraint("correo_id", "posicion", name="uq_cola_correos_adjuntos_correo_posicion"),
        CheckConstraint("tamano > 0", name="tamano_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    correo_id: Mapped[int] = mapped_column(ForeignKey("cola_correos.id", ondelete="CASCADE"))
    posicion: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(String(255))
    tipo_mime: Mapped[str] = mapped_column(String(255))
    clave: Mapped[str] = mapped_column(String(255), unique=True)
    tamano: Mapped[int] = mapped_column(Integer)


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with SessionLocal() as session:
        yield session


# En un endpoint: `def listar(db: DbSession): ...`
DbSession = Annotated[Session, Depends(get_db)]
