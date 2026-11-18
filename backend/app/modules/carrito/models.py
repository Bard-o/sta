"""Modelos del carrito (RF-30, SUP-15).

El carrito persiste en la base de datos por cliente y no bloquea sillas: las sillas se
bloquean al iniciar la compra (HU-25). Una `SeleccionCarrito` es un trayecto único o
completo con su cantidad de viajeros; cada `TramoSeleccion` guarda el vuelo, la clase y el
precio que vio el cliente al agregar o modificar la selección.

No hay relaciones ORM, como en el resto del backend: el service consulta y borra de forma
explícita. El `ON DELETE CASCADE` del tramo mantiene el carrito consistente al quitar una
selección o vaciarlo.
"""

from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

Clase = Literal["economica", "primera"]

# Tope técnico de un cuerpo de la API; el tope de negocio de 5 tiquetes activos por vuelo
# (RF-32) lo valida el service con `reservas.service.validar_limite_de_tiquetes`.
MAX_VIAJEROS_SELECCION = 20


class SeleccionCarrito(TimestampMixin, Base):
    """Trayecto único o completo que el cliente dejó en su carrito (HU-22, HU-23).

    `creado_en` es lo que la API devuelve como `agregada_en`: la fecha en que se agregó o
    modificó la selección se conserva al cambiarla.
    """

    __tablename__ = "selecciones_carrito"
    __table_args__ = (
        CheckConstraint(
            f"viajeros BETWEEN 1 AND {MAX_VIAJEROS_SELECCION}", name="viajeros_validos"
        ),
        Index(
            "ix_selecciones_carrito_cliente_creado_en",
            "cliente_id",
            "creado_en",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    viajeros: Mapped[int] = mapped_column(Integer)


class TramoSeleccion(Base):
    """Vuelo, clase y precio de referencia de una selección del carrito (RF-30, RF-33).

    `precio_al_agregar` es el precio vigente que vio el cliente al agregar o modificar la
    selección; cada lectura lo compara con el precio de hoy para avisar si cambió. `orden`
    distingue la ida (1) del regreso (2).
    """

    __tablename__ = "tramos_carrito"
    __table_args__ = (
        CheckConstraint("orden BETWEEN 1 AND 2", name="orden_valido"),
        CheckConstraint("precio_al_agregar > 0", name="precio_al_agregar_positivo"),
        UniqueConstraint("seleccion_id", "orden", name="uq_tramos_carrito_seleccion_orden"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seleccion_id: Mapped[int] = mapped_column(
        ForeignKey("selecciones_carrito.id", ondelete="CASCADE")
    )
    vuelo_id: Mapped[int] = mapped_column(ForeignKey("vuelos.id"), index=True)
    clase: Mapped[Clase] = mapped_column(
        Enum(
            "economica",
            "primera",
            name="clase_tramo_carrito",
            native_enum=False,
            length=9,
            create_constraint=True,
        )
    )
    precio_al_agregar: Mapped[int] = mapped_column(Integer)
    orden: Mapped[int] = mapped_column(Integer)
