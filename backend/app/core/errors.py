"""Formato único de error de la API.

Los módulos lanzan estas excepciones; nunca arman la respuesta de error a mano.

    {"error": {"codigo": "...", "mensaje": "...", "campos": {"campo": "..."}}}
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorDetalle(BaseModel):
    codigo: str
    mensaje: str
    campos: dict[str, str] | None = None


class ErrorRespuesta(BaseModel):
    error: ErrorDetalle


class AppError(Exception):
    """Error de negocio con código estable para el frontend y mensaje en español."""

    status_code: int = 400
    codigo: str = "solicitud_invalida"
    mensaje: str = "La solicitud no es válida."

    def __init__(
        self,
        mensaje: str | None = None,
        *,
        codigo: str | None = None,
        campos: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.mensaje = mensaje or self.mensaje
        self.codigo = codigo or self.codigo
        self.campos = campos
        self.headers = headers
        super().__init__(self.mensaje)


class SolicitudInvalida(AppError):
    status_code = 400


class NoAutenticado(AppError):
    status_code = 401
    codigo = "no_autenticado"
    mensaje = "Inicia sesión para continuar."


class SinPermiso(AppError):
    status_code = 403
    codigo = "sin_permiso"
    mensaje = "Tu rol no tiene permiso para esta acción."


class NoEncontrado(AppError):
    status_code = 404
    codigo = "no_encontrado"
    mensaje = "El recurso no existe."


class Conflicto(AppError):
    status_code = 409
    codigo = "conflicto"
    mensaje = "La operación entra en conflicto con el estado actual."


class DatosInvalidos(AppError):
    status_code = 422
    codigo = "datos_invalidos"
    mensaje = "Revisa los campos marcados."


class DemasiadosIntentos(AppError):
    status_code = 429
    codigo = "demasiados_intentos"
    mensaje = "Hiciste demasiados intentos. Espera un momento y vuelve a intentarlo."


# Respuestas de error documentadas en OpenAPI, para que los tipos generados las conozcan.
RESPUESTAS_ERROR: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorRespuesta, "description": "Solicitud inválida"},
    401: {"model": ErrorRespuesta, "description": "Sin sesión o sesión vencida"},
    403: {"model": ErrorRespuesta, "description": "El rol no tiene permiso"},
    422: {"model": ErrorRespuesta, "description": "Datos inválidos"},
}

_ESTADOS_HTTP = {
    400: ("solicitud_invalida", "La solicitud no es válida."),
    401: ("no_autenticado", "Inicia sesión para continuar."),
    403: ("sin_permiso", "Tu rol no tiene permiso para esta acción."),
    404: ("no_encontrado", "El recurso no existe."),
    405: ("metodo_no_permitido", "El método no está permitido en esta ruta."),
    409: ("conflicto", "La operación entra en conflicto con el estado actual."),
    429: ("demasiados_intentos", "Hiciste demasiados intentos. Espera un momento."),
}

_MENSAJES_VALIDACION = {
    "missing": "Este campo es obligatorio.",
    "string_too_short": "Es demasiado corto.",
    "string_too_long": "Es demasiado largo.",
    "int_parsing": "Debe ser un número entero.",
    "int_type": "Debe ser un número entero.",
    "greater_than": "Debe ser mayor que {gt}.",
    "less_than": "Debe ser menor que {lt}.",
    "json_invalid": "El cuerpo no es un JSON válido.",
}


def _respuesta(
    status_code: int,
    codigo: str,
    mensaje: str,
    campos: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    cuerpo = ErrorRespuesta(error=ErrorDetalle(codigo=codigo, mensaje=mensaje, campos=campos))
    return JSONResponse(
        status_code=status_code,
        content=cuerpo.model_dump(exclude_none=True),
        headers=headers,
    )


def _mensaje_validacion(error: dict[str, Any]) -> str:
    plantilla = _MENSAJES_VALIDACION.get(error["type"])
    if plantilla is None:
        return "El valor no es válido."
    try:
        return plantilla.format(**error.get("ctx", {}))
    except KeyError:
        return "El valor no es válido."


def _campos_de_validacion(exc: RequestValidationError) -> dict[str, str]:
    campos: dict[str, str] = {}
    for error in exc.errors():
        # loc = ("body", "campo", ...) o ("query", "campo"): se omite el origen.
        ruta = [str(parte) for parte in error["loc"][1:]] or [str(error["loc"][0])]
        campos.setdefault(".".join(ruta), _mensaje_validacion(error))
    return campos


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _respuesta(exc.status_code, exc.codigo, exc.mensaje, exc.campos, exc.headers)

    @app.exception_handler(RequestValidationError)
    def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _respuesta(
            422, DatosInvalidos.codigo, DatosInvalidos.mensaje, _campos_de_validacion(exc)
        )

    @app.exception_handler(StarletteHTTPException)
    def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo, mensaje = _ESTADOS_HTTP.get(
            exc.status_code, ("error_http", "Error en la solicitud.")
        )
        return _respuesta(exc.status_code, codigo, mensaje, headers=exc.headers)

    @app.exception_handler(Exception)
    def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado", exc_info=exc)
        return _respuesta(500, "error_interno", "Ocurrió un error inesperado. Intenta de nuevo.")
