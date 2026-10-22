from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.core.security import Rol

# Tipos de documento colombianos más el pasaporte (RF-03).
TIPOS_DOCUMENTO = ("CC", "TI", "RC", "CE", "PA")
GENEROS = ("femenino", "masculino", "otro")


class Usuario(TimestampMixin, Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        # SUP-18: el nombre de usuario es único en todo el sistema; el correo y el documento,
        # dentro de cada rol (un administrador puede tener además su cuenta de cliente).
        UniqueConstraint("rol", "email", name="uq_usuarios_rol_email"),
        UniqueConstraint(
            "rol", "tipo_documento", "numero_documento", name="uq_usuarios_rol_documento"
        ),
        Index("uq_usuarios_nombre_usuario_lower", text("lower(nombre_usuario)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_usuario: Mapped[str] = mapped_column(String(50), unique=True)
    # El root solo tiene identificador y contraseña (RF-01): por eso el correo es opcional.
    email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[Rol] = mapped_column(
        Enum(
            Rol,
            name="rol",
            native_enum=False,
            length=10,
            create_constraint=True,
            values_callable=lambda roles: [r.value for r in roles],
        )
    )
    email_verificado: Mapped[bool] = mapped_column(Boolean, server_default=false())
    # Borrado lógico (RF-02, RF-10): una cuenta inactiva no inicia sesión.
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())
    # Se incrementa para invalidar en el servidor todas las sesiones abiertas (HU-04, RF-07).
    version_sesion: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    # HU-01: datos personales del cliente. Son opcionales en la base porque el root y el
    # administrador con el registro incompleto (HU-12) todavía no los tienen.
    tipo_documento: Mapped[str | None] = mapped_column(
        Enum(
            *TIPOS_DOCUMENTO,
            name="tipo_documento",
            native_enum=False,
            length=2,
            create_constraint=True,
        )
    )
    numero_documento: Mapped[str | None] = mapped_column(String(20))
    nombres: Mapped[str | None] = mapped_column(String(100))
    apellidos: Mapped[str | None] = mapped_column(String(100))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    lugar_nacimiento: Mapped[str | None] = mapped_column(String(120))
    direccion_facturacion: Mapped[str | None] = mapped_column(String(200))
    genero: Mapped[str | None] = mapped_column(
        Enum(
            *GENEROS,
            name="genero",
            native_enum=False,
            length=9,
            create_constraint=True,
        )
    )
    telefono: Mapped[str | None] = mapped_column(String(20))
    # Ley 1581 de 2012 (RF-03): se guarda cuándo aceptó la política de tratamiento de datos.
    fecha_aceptacion_politica: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TokenVerificacion(TimestampMixin, Base):
    """Enlace de verificación de correo (HU-01, HU-02, HU-07).

    Se guarda solo el hash del token: el valor en claro viaja únicamente en el correo.
    """

    __tablename__ = "tokens_verificacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Correo que se verifica: en HU-07 puede ser uno nuevo, todavía pendiente.
    email: Mapped[str] = mapped_column(String(254))
    # SUP-19: vence en 24 horas y es de un solo uso.
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
