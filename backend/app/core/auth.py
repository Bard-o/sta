"""Sesión en cookie httpOnly y control de acceso por rol (RF-11, RNF-10, RNF-14).

Uso en un router:

    @router.get("/algo")
    def algo(usuario: UsuarioSesion): ...

    @router.post("/reservas")
    def reservar(usuario: Annotated[UsuarioActual, Depends(require_role(Rol.CLIENTE))]): ...

    @router.post("/vuelos", dependencies=[Depends(require_role(Rol.ADMIN))])
    def crear_vuelo(...): ...

HU-12, RF-02: un administrador con el registro incompleto solo puede iniciar y cerrar sesión,
consultar /auth/me y completar su registro. Cualquier otra ruta que use la sesión responde
403 `registro_incompleto`; el bloqueo vive aquí, así que cubre los endpoints de todos los módulos
sin que cada router lo marque.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request, Response

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import NoAutenticado, RegistroIncompleto, SinPermiso
from app.core.security import Rol, crear_token, leer_token, minutos_de_sesion

# Cada petición autenticada renueva la cookie (vencimiento por inactividad), como mucho
# una vez por este intervalo para no reescribirla en cada llamada.
_RENOVAR_CADA = timedelta(seconds=60)

# HU-12, RF-02: lo único que puede usar un administrador con el registro incompleto. Rutas
# completas, con el prefijo de app.main.API_PREFIX. El endpoint de registro lo implementa
# usuarios (#26) y no necesita marcar nada en su router.
PREFIJOS_PERMITIDOS_CON_REGISTRO_INCOMPLETO: tuple[str, ...] = ("/api/v1/auth/",)
RUTAS_PERMITIDAS_CON_REGISTRO_INCOMPLETO: frozenset[tuple[str, str]] = frozenset(
    {("POST", "/api/v1/administradores/me/registro")}
)


def permitida_con_registro_incompleto(metodo: str, ruta: str) -> bool:
    """True si un administrador con el registro incompleto puede llamar `metodo ruta`."""
    return ruta.startswith(PREFIJOS_PERMITIDOS_CON_REGISTRO_INCOMPLETO) or (
        (metodo.upper(), ruta) in RUTAS_PERMITIDAS_CON_REGISTRO_INCOMPLETO
    )


@dataclass(frozen=True)
class UsuarioActual:
    id: int
    nombre_usuario: str
    rol: Rol


def poner_cookie_sesion(response: Response, usuario_id: int, rol: Rol, version_sesion: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=crear_token(usuario_id, rol, version_sesion),
        max_age=minutos_de_sesion(rol) * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def borrar_cookie_sesion(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def get_current_user(request: Request, response: Response, db: DbSession) -> UsuarioActual:
    """Usuario de la sesión. Responde 401 si no hay sesión válida y 403 `registro_incompleto` a un
    administrador sin registro completo fuera de las rutas permitidas (HU-12)."""
    # Import diferido: core no depende de usuarios al importarse.
    from app.modules.usuarios import service as usuarios_service

    token = request.cookies.get(get_settings().cookie_name)
    datos = leer_token(token) if token else None
    if datos is None:
        raise NoAutenticado()

    usuario = usuarios_service.obtener_usuario_para_sesion(db, datos.usuario_id)
    if (
        usuario is None
        or not usuario.activo
        or usuario.version_sesion != datos.version_sesion
        or usuario.rol != datos.rol
    ):
        raise NoAutenticado()

    # HU-12, RF-02: mientras no complete su registro, el administrador solo puede iniciar y
    # cerrar sesión, consultar /auth/me y completar el registro.
    if (
        usuario.rol == Rol.ADMIN
        and not usuario.registro_completo
        and not permitida_con_registro_incompleto(request.method, request.url.path)
    ):
        raise RegistroIncompleto()

    if datetime.now(UTC) - datos.emitido_en >= _RENOVAR_CADA:
        poner_cookie_sesion(response, usuario.id, usuario.rol, usuario.version_sesion)

    return UsuarioActual(id=usuario.id, nombre_usuario=usuario.nombre_usuario, rol=usuario.rol)


UsuarioSesion = Annotated[UsuarioActual, Depends(get_current_user)]


def require_role(*roles: Rol) -> Callable[..., UsuarioActual]:
    """Dependencia que exige uno de los roles dados (403 si el rol no está permitido)."""
    permitidos = frozenset(roles)

    def dependencia(usuario: UsuarioSesion) -> UsuarioActual:
        if usuario.rol not in permitidos:
            raise SinPermiso()
        return usuario

    return dependencia


def get_current_user_opcional(
    request: Request, response: Response, db: DbSession
) -> UsuarioActual | None:
    """Como get_current_user, pero devuelve None para visitantes en vez de responder 401.

    El bloqueo por registro incompleto (HU-12) también aplica."""
    try:
        return get_current_user(request, response, db)
    except NoAutenticado:
        return None


UsuarioOpcional = Annotated[UsuarioActual | None, Depends(get_current_user_opcional)]
