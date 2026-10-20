"""Endpoints del módulo noticias. Contrato: docs/api/iteracion-1.md (HU-19).

Los endpoints que responden NoImplementado (501) son stubs del contrato; su implementación
llega con el issue de la HU.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import DbSession
from app.core.errors import NoImplementado
from app.modules.noticias.schemas import Noticia, PaginaNoticias

router = APIRouter(prefix="/noticias", tags=["noticias"])


@router.get("", response_model=PaginaNoticias)
def listar_noticias(
    db: DbSession,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=50)] = 10,
) -> PaginaNoticias:
    """Noticias de la más reciente a la más antigua; público (HU-19, RF-55)."""
    raise NoImplementado()


@router.get("/carrusel", response_model=list[Noticia])
def obtener_carrusel(db: DbSession) -> list[Noticia]:
    """Hasta 10 elementos: promociones vigentes y luego vuelos recientes (HU-19, RF-22)."""
    raise NoImplementado()
