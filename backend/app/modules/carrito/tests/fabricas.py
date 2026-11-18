"""Fábricas de selecciones del carrito para los tests.

Escriben filas directamente, sin pasar por los endpoints de #126, para preparar estados que
solo se alcanzan cuando otro cliente compra o cuando el vuelo cambia después de agregar.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.carrito.models import SeleccionCarrito, TramoSeleccion
from app.modules.vuelos.models import Clase, Vuelo


def crear_seleccion(
    db: Session,
    cliente_id: int,
    vuelos: Sequence[Vuelo],
    *,
    clases: Sequence[Clase] | None = None,
    viajeros: int = 1,
    precios_al_agregar: Sequence[int] | None = None,
    agregada_en: datetime | None = None,
) -> SeleccionCarrito:
    """Crea una selección con sus tramos; el precio de referencia sale del vuelo si falta."""
    if clases is None:
        clases = ["economica"] * len(vuelos)
    if precios_al_agregar is None:
        precios_al_agregar = [
            vuelo.precio_primera if clase == "primera" else vuelo.precio_economica
            for vuelo, clase in zip(vuelos, clases, strict=True)
        ]

    seleccion = SeleccionCarrito(cliente_id=cliente_id, viajeros=viajeros)
    db.add(seleccion)
    db.flush()
    for orden, (vuelo, clase, precio) in enumerate(
        zip(vuelos, clases, precios_al_agregar, strict=True), start=1
    ):
        db.add(
            TramoSeleccion(
                seleccion_id=seleccion.id,
                vuelo_id=vuelo.id,
                clase=clase,
                precio_al_agregar=precio,
                orden=orden,
            )
        )
    if agregada_en is not None:
        seleccion.creado_en = agregada_en
    db.flush()
    return seleccion
