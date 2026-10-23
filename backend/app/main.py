"""Aplicación FastAPI del STA."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core import health
from app.core.config import get_settings
from app.core.errors import RESPUESTAS_ERROR, registrar_manejadores
from app.core.planificador import cargar_tareas_de_modulos, planificador
from app.modules.noticias.router import router as noticias_router
from app.modules.usuarios.router import router as usuarios_router
from app.modules.vuelos.router import router as vuelos_router

API_PREFIX = "/api/v1"


def _operation_id(route: APIRoute) -> str:
    # operationId legible y estable para los tipos generados del frontend (gen:api).
    return route.name


@asynccontextmanager
async def _ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    # Solo maneja el hilo del planificador; no toca la base de datos.
    activo = get_settings().planificador_activo
    if activo:
        cargar_tareas_de_modulos()
        planificador.iniciar()
    try:
        yield
    finally:
        if activo:
            planificador.detener()


def create_app() -> FastAPI:
    app = FastAPI(
        title="STA · Sistema de Tiquetes Aéreos",
        version="0.1.0",
        generate_unique_id_function=_operation_id,
        responses=RESPUESTAS_ERROR,
        lifespan=_ciclo_de_vida,
    )
    registrar_manejadores(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(usuarios_router, prefix=API_PREFIX)
    app.include_router(vuelos_router, prefix=API_PREFIX)
    app.include_router(noticias_router, prefix=API_PREFIX)
    return app


app = create_app()
