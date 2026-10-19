from fastapi import APIRouter, Response, status

from app.core.auth import (
    UsuarioOpcional,
    UsuarioSesion,
    borrar_cookie_sesion,
    poner_cookie_sesion,
)
from app.core.db import DbSession
from app.modules.usuarios import service
from app.modules.usuarios.schemas import LoginEntrada, UsuarioSalida

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UsuarioSalida)
def login(datos: LoginEntrada, response: Response, db: DbSession) -> UsuarioSalida:
    """Inicia sesión con nombre de usuario (o correo) y contraseña (RF-06, HU-03)."""
    usuario = service.autenticar(db, datos.usuario, datos.contrasena)
    poner_cookie_sesion(response, usuario.id, usuario.rol, usuario.version_sesion)
    return UsuarioSalida.model_validate(usuario)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, usuario: UsuarioOpcional, db: DbSession) -> None:
    """Cierra la sesión en el servidor y borra la cookie (HU-04)."""
    if usuario is not None:
        service.cerrar_sesiones(db, usuario.id)
    borrar_cookie_sesion(response)


@router.get("/me", response_model=UsuarioSalida)
def me(usuario: UsuarioSesion, db: DbSession) -> UsuarioSalida:
    """Usuario de la sesión actual."""
    return UsuarioSalida.model_validate(service.obtener_usuario_para_sesion(db, usuario.id))
