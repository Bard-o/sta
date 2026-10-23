"""Endpoints del módulo usuarios. Contrato: docs/api/iteracion-1.md (HU-01 a HU-12).

Los endpoints que responden NoImplementado (501) son stubs del contrato: ya validan el rol y
el cuerpo, y su implementación llega con el issue de cada HU.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.core.auth import (
    UsuarioActual,
    UsuarioOpcional,
    UsuarioSesion,
    borrar_cookie_sesion,
    poner_cookie_sesion,
    require_role,
)
from app.core.db import DbSession
from app.core.errors import NoImplementado, SinPermiso, respuestas_error
from app.core.security import Rol
from app.modules.usuarios import service
from app.modules.usuarios.schemas import (
    AdministradorEntrada,
    AdministradorSalida,
    BloqueoDesactivacion,
    CambioContrasenaEntrada,
    DesactivacionSalida,
    LoginEntrada,
    MensajeSalida,
    PerfilEntrada,
    PerfilSalida,
    RegistroAdministradorEntrada,
    RegistroClienteEntrada,
    RestablecimientoConfirmacion,
    RestablecimientoSolicitud,
    SuscripcionEntrada,
    SuscripcionSalida,
    TokenEntrada,
    UsuarioSalida,
)

Cliente = Annotated[UsuarioActual, Depends(require_role(Rol.CLIENTE))]
ClienteOAdmin = Annotated[UsuarioActual, Depends(require_role(Rol.CLIENTE, Rol.ADMIN))]
Admin = Annotated[UsuarioActual, Depends(require_role(Rol.ADMIN))]
Root = Annotated[UsuarioActual, Depends(require_role(Rol.ROOT))]


def solo_visitante(usuario: UsuarioOpcional) -> None:
    """HU-01, Apéndice B: el registro de clientes es solo para visitantes.

    Con una sesión abierta responde 403 sin_permiso. (Esto no va en el docstring del endpoint:
    ese texto sale en el OpenAPI y cambiaría los tipos generados del frontend.)
    """
    if usuario is not None:
        raise SinPermiso()


# ---------- Sesión: /auth ----------

auth = APIRouter(prefix="/auth", tags=["auth"])


@auth.post("/login", response_model=UsuarioSalida, responses=respuestas_error(429))
def login(datos: LoginEntrada, response: Response, db: DbSession) -> UsuarioSalida:
    """Inicia sesión con nombre de usuario (o correo) y contraseña (RF-06, HU-03)."""
    usuario = service.autenticar(db, datos.usuario, datos.contrasena)
    poner_cookie_sesion(response, usuario.id, usuario.rol, usuario.version_sesion)
    return UsuarioSalida.model_validate(usuario)


@auth.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, usuario: UsuarioOpcional, db: DbSession) -> None:
    """Cierra la sesión en el servidor y borra la cookie (HU-04)."""
    if usuario is not None:
        service.cerrar_sesiones(db, usuario.id)
    borrar_cookie_sesion(response)


@auth.get("/me", response_model=UsuarioSalida)
def me(usuario: UsuarioSesion, db: DbSession) -> UsuarioSalida:
    """Usuario de la sesión actual."""
    return UsuarioSalida.model_validate(service.obtener_usuario_para_sesion(db, usuario.id))


@auth.post("/restablecimiento", status_code=status.HTTP_202_ACCEPTED, response_model=MensajeSalida)
def solicitar_restablecimiento(datos: RestablecimientoSolicitud, db: DbSession) -> MensajeSalida:
    """Envía el enlace para restablecer la contraseña si el correo existe (HU-05, RF-07).

    Responde lo mismo exista o no el correo.
    """
    service.solicitar_restablecimiento(db, datos.email)
    return MensajeSalida(mensaje=service.MENSAJE_RESTABLECIMIENTO)


@auth.post(
    "/restablecimiento/confirmar",
    status_code=status.HTTP_204_NO_CONTENT,
)
def confirmar_restablecimiento(datos: RestablecimientoConfirmacion, db: DbSession) -> None:
    """Define la contraseña nueva con el token del enlace y cierra todas las sesiones (HU-05)."""
    service.confirmar_restablecimiento(
        db,
        datos.token,
        contrasena_nueva=datos.contrasena_nueva,
        confirmacion=datos.confirmacion,
    )


# ---------- Cuenta propia: /usuarios ----------

cuenta = APIRouter(prefix="/usuarios", tags=["usuarios"])


@cuenta.post(
    "/registro",
    status_code=status.HTTP_201_CREATED,
    response_model=UsuarioSalida,
    responses=respuestas_error(409),
    dependencies=[Depends(solo_visitante)],
)
def registrar_cliente(
    datos: RegistroClienteEntrada, response: Response, db: DbSession
) -> UsuarioSalida:
    """Registra un cliente, inicia su sesión y envía el enlace de verificación (HU-01)."""
    nuevo = service.registrar_cliente(db, datos)
    poner_cookie_sesion(response, nuevo.id, nuevo.rol, nuevo.version_sesion)
    return UsuarioSalida.model_validate(nuevo)


@cuenta.post("/verificacion", status_code=status.HTTP_204_NO_CONTENT)
def verificar_correo(datos: TokenEntrada, db: DbSession) -> None:
    """Marca el correo como verificado con el token del enlace (HU-02)."""
    service.verificar_correo(db, datos.token)


@cuenta.post(
    "/me/verificacion/reenviar",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=respuestas_error(409),
)
def reenviar_verificacion(usuario: ClienteOAdmin, db: DbSession) -> None:
    """Envía un enlace nuevo e invalida el anterior (HU-02)."""
    service.reenviar_verificacion(db, usuario.id)


@cuenta.put("/me/contrasena", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_contrasena(
    datos: CambioContrasenaEntrada, usuario: UsuarioSesion, db: DbSession
) -> None:
    """Cambia la contraseña indicando la actual (HU-06). Único modo para el root."""
    service.cambiar_contrasena(
        db,
        usuario.id,
        contrasena_actual=datos.contrasena_actual,
        contrasena_nueva=datos.contrasena_nueva,
        confirmacion=datos.confirmacion,
    )


@cuenta.get("/me/perfil", response_model=PerfilSalida)
def obtener_perfil(usuario: ClienteOAdmin, db: DbSession) -> PerfilSalida:
    """Perfil del cliente o administrador de la sesión (HU-07)."""
    raise NoImplementado()


@cuenta.put("/me/perfil", response_model=PerfilSalida, responses=respuestas_error(409))
def actualizar_perfil(datos: PerfilEntrada, usuario: ClienteOAdmin, db: DbSession) -> PerfilSalida:
    """Actualiza el perfil. Un correo nuevo queda pendiente hasta verificarse (HU-07)."""
    raise NoImplementado()


@cuenta.put("/me/imagen", response_model=PerfilSalida)
def subir_imagen_perfil(
    imagen: Annotated[UploadFile, File(description="JPG o PNG, máximo 2 MB.")],
    usuario: ClienteOAdmin,
    db: DbSession,
) -> PerfilSalida:
    """Sube o reemplaza la imagen de perfil (HU-01, HU-07)."""
    raise NoImplementado()


@cuenta.get(
    "/me/imagen",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}, **respuestas_error(404)},
)
def obtener_imagen_perfil(usuario: ClienteOAdmin, db: DbSession) -> Response:
    """Imagen de perfil de la sesión (la URL que trae `imagen_url`)."""
    raise NoImplementado()


@cuenta.delete("/me/imagen", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_imagen_perfil(usuario: ClienteOAdmin, db: DbSession) -> None:
    """Quita la imagen de perfil."""
    raise NoImplementado()


@cuenta.put("/me/suscripcion", response_model=SuscripcionSalida)
def cambiar_suscripcion(
    datos: SuscripcionEntrada, usuario: Cliente, db: DbSession
) -> SuscripcionSalida:
    """Suscribe o da de baja al cliente del correo de noticias (HU-08, RF-09)."""
    raise NoImplementado()


@cuenta.post("/suscripcion/baja", status_code=status.HTTP_204_NO_CONTENT)
def dar_baja_suscripcion(datos: TokenEntrada, db: DbSession) -> None:
    """Baja de noticias con el enlace del correo, sin iniciar sesión (HU-08, RF-56)."""
    raise NoImplementado()


@cuenta.get("/me/desactivacion", response_model=DesactivacionSalida)
def consultar_desactivacion(usuario: Cliente, db: DbSession) -> DesactivacionSalida:
    """Indica si la cuenta se puede desactivar y qué lo impide (HU-09)."""
    bloqueos = [
        BloqueoDesactivacion.model_validate(bloqueo, from_attributes=True)
        for bloqueo in service.bloqueos_de_desactivacion(db, usuario.id)
    ]
    return DesactivacionSalida(puede_desactivar=not bloqueos, bloqueos=bloqueos)


@cuenta.post(
    "/me/desactivacion",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=respuestas_error(409),
)
def desactivar_cuenta(usuario: Cliente, response: Response, db: DbSession) -> None:
    """Desactiva la cuenta (borrado lógico) y cierra la sesión (HU-09, RF-10)."""
    service.desactivar_cuenta(db, usuario.id)
    borrar_cookie_sesion(response)


# ---------- Administradores: /administradores ----------

administradores = APIRouter(prefix="/administradores", tags=["administradores"])


@administradores.get("", response_model=list[AdministradorSalida])
def listar_administradores(usuario: Root, db: DbSession) -> list[AdministradorSalida]:
    """Administradores con su estado (HU-11)."""
    raise NoImplementado()


@administradores.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AdministradorSalida,
    responses=respuestas_error(409),
)
def crear_administrador(
    datos: AdministradorEntrada, usuario: Root, db: DbSession
) -> AdministradorSalida:
    """Crea un administrador con contraseña temporal (HU-10, RF-02)."""
    raise NoImplementado()


@administradores.post(
    "/{admin_id}/desactivar",
    response_model=AdministradorSalida,
    responses=respuestas_error(404, 409),
)
def desactivar_administrador(admin_id: int, usuario: Root, db: DbSession) -> AdministradorSalida:
    """Desactiva un administrador y cierra sus sesiones (HU-11)."""
    raise NoImplementado()


@administradores.post(
    "/{admin_id}/reactivar",
    response_model=AdministradorSalida,
    responses=respuestas_error(404, 409),
)
def reactivar_administrador(admin_id: int, usuario: Root, db: DbSession) -> AdministradorSalida:
    """Reactiva un administrador desactivado (HU-11)."""
    raise NoImplementado()


@administradores.post("/me/registro", response_model=UsuarioSalida, responses=respuestas_error(409))
def completar_registro_administrador(
    datos: RegistroAdministradorEntrada, usuario: Admin, response: Response, db: DbSession
) -> UsuarioSalida:
    """Completa los datos del administrador y cambia la contraseña temporal (HU-12)."""
    raise NoImplementado()


router = APIRouter()
router.include_router(auth)
router.include_router(cuenta)
router.include_router(administradores)
