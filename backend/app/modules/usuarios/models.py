from sqlalchemy import Boolean, Enum, Integer, String, UniqueConstraint, false, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.core.security import Rol


class Usuario(TimestampMixin, Base):
    __tablename__ = "usuarios"
    # SUP-18: el nombre de usuario es único en todo el sistema; el correo, dentro de cada rol.
    __table_args__ = (UniqueConstraint("rol", "email", name="uq_usuarios_rol_email"),)

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
