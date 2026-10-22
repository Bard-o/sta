"""Interfaz pública del módulo usuarios. Otros módulos solo llaman a estas funciones."""

from dataclasses import dataclass

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError, DatosInvalidos, NoAutenticado
from app.core.security import (
    MENSAJE_POLITICA_CONTRASENA,
    Rol,
    cumple_politica_contrasena,
    hash_contrasena,
    verificar_contrasena,
)
from app.modules.usuarios.models import Usuario


class CredencialesInvalidas(AppError):
    # RF-06: el mensaje no revela si falló el usuario o la contraseña.
    status_code = 401
    codigo = "credenciales_invalidas"
    mensaje = "Usuario o contraseña incorrectos."


class CuentaInactiva(AppError):
    status_code = 403
    codigo = "cuenta_inactiva"
    mensaje = "Cuenta inactiva."


class ContrasenaActualIncorrecta(AppError):
    # HU-06: la contraseña actual no coincide; no se cambia nada.
    status_code = 422
    codigo = "contrasena_actual_incorrecta"
    mensaje = "La contraseña actual es incorrecta."


def autenticar(db: Session, identificador: str, contrasena: str) -> Usuario:
    """Valida nombre de usuario (o correo) y contraseña. Lanza CredencialesInvalidas o
    CuentaInactiva."""
    clave = identificador.strip().lower()
    candidatos = db.scalars(
        select(Usuario).where(
            # Los correos se guardan en minúscula.
            or_(func.lower(Usuario.nombre_usuario) == clave, Usuario.email == clave)
        )
    ).all()

    if not candidatos:
        verificar_contrasena(contrasena, None)  # mismo tiempo de respuesta que un fallo real
        raise CredencialesInvalidas()

    # Un mismo correo puede tener una cuenta de cliente y otra de administrador (SUP-18).
    usuario = next(
        (u for u in candidatos if verificar_contrasena(contrasena, u.password_hash)), None
    )
    if usuario is None:
        raise CredencialesInvalidas()
    if not usuario.activo:
        raise CuentaInactiva()
    return usuario


def obtener_usuario_para_sesion(db: Session, usuario_id: int) -> Usuario | None:
    return db.get(Usuario, usuario_id)


def cerrar_sesiones(db: Session, usuario_id: int) -> None:
    """Invalida todas las sesiones abiertas del usuario."""
    db.execute(
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(version_sesion=Usuario.version_sesion + 1)
    )
    db.commit()


def _validar_contrasena_nueva(contrasena_nueva: str, confirmacion: str) -> None:
    """RNF-08 y confirmación (HU-06, HU-05): lanza DatosInvalidos con el campo que falla."""
    if not cumple_politica_contrasena(contrasena_nueva):
        raise DatosInvalidos(campos={"contrasena_nueva": MENSAJE_POLITICA_CONTRASENA})
    if contrasena_nueva != confirmacion:
        raise DatosInvalidos(campos={"confirmacion": "Las contraseñas no coinciden."})


def cambiar_contrasena(
    db: Session,
    usuario_id: int,
    *,
    contrasena_actual: str,
    contrasena_nueva: str,
    confirmacion: str,
) -> None:
    """Cambia la contraseña indicando la actual (HU-06, RF-08).

    Las reglas sin estado se validan primero para que el usuario corrija la contraseña nueva
    antes de preocuparse por la actual. La sesión actual sigue abierta: no se incrementa
    `version_sesion` (a diferencia del restablecimiento, que cierra todas las sesiones).
    """
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()

    _validar_contrasena_nueva(contrasena_nueva, confirmacion)

    if not verificar_contrasena(contrasena_actual, usuario.password_hash):
        raise ContrasenaActualIncorrecta(
            campos={"contrasena_actual": "La contraseña actual es incorrecta."}
        )

    usuario.password_hash = hash_contrasena(contrasena_nueva)
    db.commit()


def crear_usuario(
    db: Session,
    *,
    nombre_usuario: str,
    contrasena: str,
    rol: Rol,
    email: str | None = None,
    email_verificado: bool = False,
    activo: bool = True,
) -> Usuario:
    usuario = Usuario(
        nombre_usuario=nombre_usuario,
        email=email.strip().lower() if email else None,
        password_hash=hash_contrasena(contrasena),
        rol=rol,
        email_verificado=email_verificado,
        activo=activo,
    )
    db.add(usuario)
    db.commit()
    return usuario


def asegurar_root(db: Session, nombre_usuario: str, contrasena: str) -> bool:
    """Crea el único usuario root si no existe (RF-01). Devuelve True si lo creó."""
    existe = db.scalar(select(Usuario.id).where(Usuario.rol == Rol.ROOT).limit(1))
    if existe is not None:
        return False
    crear_usuario(db, nombre_usuario=nombre_usuario, contrasena=contrasena, rol=Rol.ROOT)
    return True


@dataclass(frozen=True)
class SuscriptorNoticias:
    usuario_id: int
    email: str
    nombres: str
    # Va en el enlace «cancelar suscripción» del correo: POST /usuarios/suscripcion/baja.
    token_baja: str


def suscriptores_noticias(db: Session) -> list[SuscriptorNoticias]:
    """Clientes activos, con el correo verificado y suscritos a noticias (RF-09, RF-56).

    La usa noticias para enviar el correo de cada noticia nueva.
    """
    raise NotImplementedError("HU-08")
