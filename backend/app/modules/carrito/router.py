"""Endpoints del módulo carrito. Contrato: docs/api/iteracion-2.md (HU-22 y HU-23).

Comprueban la sesión, el rol y el cuerpo; la lógica del carrito vive en `service.py`. Todo
es solo del cliente y cada cliente ve y modifica únicamente su propio carrito.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.auth import UsuarioActual, require_role
from app.core.db import DbSession
from app.core.errors import respuestas_error
from app.core.security import Rol
from app.modules.carrito import service
from app.modules.carrito.schemas import (
    Carrito,
    SeleccionCambio,
    SeleccionCarrito,
    SeleccionEntrada,
)

Cliente = Annotated[UsuarioActual, Depends(require_role(Rol.CLIENTE))]

router = APIRouter(prefix="/carrito", tags=["carrito"])


@router.get("", response_model=Carrito)
def obtener_carrito(usuario: Cliente, db: DbSession) -> Carrito:
    """El carrito del cliente con el precio y la disponibilidad de hoy (HU-23, RF-30)."""
    return service.obtener_carrito(db, usuario.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def vaciar_carrito(usuario: Cliente, db: DbSession) -> None:
    """Quita todas las selecciones del carrito (HU-23)."""
    service.vaciar_carrito(db, usuario.id)
    db.commit()


@router.post(
    "/selecciones",
    status_code=status.HTTP_201_CREATED,
    response_model=SeleccionCarrito,
    responses=respuestas_error(409),
)
def agregar_seleccion(datos: SeleccionEntrada, usuario: Cliente, db: DbSession) -> SeleccionCarrito:
    """Agrega un trayecto único o completo; valida cupo y límite de 5 (HU-22, RF-32)."""
    seleccion = service.agregar_seleccion(db, usuario.id, datos)
    db.commit()
    return seleccion


@router.patch(
    "/selecciones/{seleccion_id}",
    response_model=SeleccionCarrito,
    responses=respuestas_error(404, 409),
)
def modificar_seleccion(
    seleccion_id: int, datos: SeleccionCambio, usuario: Cliente, db: DbSession
) -> SeleccionCarrito:
    """Cambia la clase o la cantidad de viajeros y vuelve a validar (HU-23)."""
    seleccion = service.modificar_seleccion(db, usuario.id, seleccion_id, datos)
    db.commit()
    return seleccion


@router.delete(
    "/selecciones/{seleccion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=respuestas_error(404),
)
def quitar_seleccion(seleccion_id: int, usuario: Cliente, db: DbSession) -> None:
    """Quita una selección del carrito (HU-23)."""
    service.quitar_seleccion(db, usuario.id, seleccion_id)
    db.commit()
