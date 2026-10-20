"""Aplicación FastAPI del STA."""

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core import health
from app.core.errors import RESPUESTAS_ERROR, registrar_manejadores
from app.modules.usuarios.router import router as auth_router

API_PREFIX = "/api/v1"


def _operation_id(route: APIRoute) -> str:
    # operationId legible y estable para los tipos generados del frontend (gen:api).
    return route.name


def create_app() -> FastAPI:
    app = FastAPI(
        title="STA · Sistema de Tiquetes Aéreos",
        version="0.1.0",
        generate_unique_id_function=_operation_id,
        responses=RESPUESTAS_ERROR,
    )
    registrar_manejadores(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    return app


app = create_app()
