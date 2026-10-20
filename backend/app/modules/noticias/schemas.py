"""Contrato del módulo noticias (docs/api/iteracion-1.md, HU-19).

Las noticias son solo automáticas (RF-55): no hay endpoints para crearlas, editarlas ni
borrarlas. Las publica el módulo vuelos llamando a noticias.service.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ClaseNoticia = Literal["economica", "primera"]


class CiudadNoticia(BaseModel):
    codigo: str
    nombre: str
    zona_horaria: str


class PromocionNoticia(BaseModel):
    porcentaje: int
    clases: list[ClaseNoticia]
    inicio: datetime
    fin: datetime
    estado: Literal["programada", "vigente", "vencida", "agotada", "cancelada"]
    precio_economica: int | None = Field(
        description="Precio con descuento; null si la promoción no aplica a la clase."
    )
    precio_primera: int | None


class Noticia(BaseModel):
    id: int
    tipo: Literal["vuelo", "promocion"]
    titulo: str = Field(description="P. ej. «Nuevo vuelo Pereira → Cartagena».")
    publicada_en: datetime
    vigente: bool = Field(
        description="Vuelo todavía programado y, si es de promoción, promoción vigente."
    )
    vuelo_id: int = Field(description="Abre el detalle: GET /api/v1/vuelos/{vuelo_id}.")
    vuelo_codigo: str
    origen: CiudadNoticia
    destino: CiudadNoticia
    salida: datetime = Field(description="UTC.")
    precio_economica: int = Field(description="Precio base del vuelo.")
    precio_primera: int
    imagen_url: str = Field(description="Imagen de la ciudad destino (SUP-30).")
    promocion: PromocionNoticia | None


class PaginaNoticias(BaseModel):
    items: list[Noticia]
    total: int
    pagina: int
    por_pagina: int
