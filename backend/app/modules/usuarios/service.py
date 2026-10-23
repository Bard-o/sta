"""Interfaz pública del módulo usuarios. Otros módulos solo llaman a estas funciones."""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html import escape

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, DatosInvalidos, NoAutenticado
from app.core.mail import enviar_correo
from app.core.security import (
    MENSAJE_POLITICA_CONTRASENA,
    Rol,
    cumple_politica_contrasena,
    hash_contrasena,
    verificar_contrasena,
)
from app.modules.usuarios.models import TokenRestablecimiento, TokenVerificacion, Usuario
from app.modules.usuarios.schemas import RegistroClienteEntrada

logger = logging.getLogger(__name__)

# SUP-19: el enlace de verificación de correo vence en 24 horas.
HORAS_VERIFICACION = 24
# SUP-19: el enlace de restablecimiento de contraseña vence en 30 minutos.
MINUTOS_RESTABLECIMIENTO = 30
# RF-07: la solicitud responde lo mismo exista o no el correo.
MENSAJE_RESTABLECIMIENTO = (
    "Si el correo está registrado, recibirás un enlace válido por 30 minutos."
)


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


class DatosDuplicados(AppError):
    """RF-04: un dato único ya pertenece a otra cuenta; `campos` dice cuál."""

    status_code = 409
    codigo = "datos_duplicados"
    mensaje = "Alguno de los datos ya pertenece a otra cuenta."


class EnlaceInvalido(AppError):
    """HU-02, HU-05, HU-08: el token no existe, venció o ya se usó."""

    status_code = 400
    codigo = "enlace_invalido"
    mensaje = "El enlace no es válido o venció. Pide uno nuevo."


class CorreoYaVerificado(AppError):
    """HU-02: se pidió un enlace nuevo sin un correo pendiente de verificar."""

    status_code = 409
    codigo = "correo_ya_verificado"
    mensaje = "Tu correo ya está verificado."


MENSAJES_DUPLICADO = {
    "nombre_usuario": "Ese nombre de usuario ya está en uso.",
    "email": "Ese correo ya está registrado en otra cuenta de cliente.",
    "numero_documento": "Ese número de documento ya está registrado en otra cuenta de cliente.",
}

# Restricciones de la tabla usuarios que pueden saltar al registrar un cliente.
_CAMPO_POR_RESTRICCION = {
    "uq_usuarios_nombre_usuario": "nombre_usuario",
    "uq_usuarios_nombre_usuario_lower": "nombre_usuario",
    "uq_usuarios_rol_email": "email",
    "uq_usuarios_rol_documento": "numero_documento",
}


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


# ---------- Registro de clientes (HU-01) ----------


def hash_token(token: str) -> str:
    """Hash con el que se guarda un token de correo; el valor en claro solo viaja en el enlace."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def registrar_cliente(db: Session, datos: RegistroClienteEntrada) -> Usuario:
    """HU-01, RF-03 y RF-04: crea la cuenta de cliente y su token de verificación.

    Confirma la transacción y después envía el enlace con `enviar_verificacion`; si el correo
    falla, la cuenta queda creada igual. La cookie de sesión la pone el router. Lanza
    DatosInvalidos o DatosDuplicados.
    """
    _validar_datos_de_registro(datos)
    email = datos.email.strip().lower()
    nombre_usuario = datos.nombre_usuario.strip()

    campos = _campos_duplicados(
        db,
        nombre_usuario=nombre_usuario,
        email=email,
        tipo_documento=datos.tipo_documento,
        numero_documento=datos.numero_documento,
    )
    if campos:
        raise DatosDuplicados(campos=campos)

    usuario = Usuario(
        nombre_usuario=nombre_usuario,
        email=email,
        password_hash=hash_contrasena(datos.contrasena),
        rol=Rol.CLIENTE,
        email_verificado=False,
        activo=True,
        tipo_documento=datos.tipo_documento,
        numero_documento=datos.numero_documento,
        nombres=datos.nombres.strip(),
        apellidos=datos.apellidos.strip(),
        fecha_nacimiento=datos.fecha_nacimiento,
        lugar_nacimiento=datos.lugar_nacimiento.strip(),
        direccion_facturacion=datos.direccion_facturacion.strip(),
        genero=datos.genero,
        telefono=datos.telefono.strip() if datos.telefono else None,
        # Ley 1581 de 2012 (RF-03).
        fecha_aceptacion_politica=datetime.now(UTC),
    )
    db.add(usuario)
    try:
        db.flush()  # asigna el id antes de crear el token
        token = _crear_token_verificacion(db, usuario.id, email)
        db.commit()
    except IntegrityError as exc:
        # Carrera entre la verificación anterior y el commit: la restricción única decide.
        db.rollback()
        campos = _campos_duplicados(
            db,
            nombre_usuario=nombre_usuario,
            email=email,
            tipo_documento=datos.tipo_documento,
            numero_documento=datos.numero_documento,
        ) or _campo_por_restriccion(exc)
        raise DatosDuplicados(campos=campos or None) from exc

    enviar_verificacion(usuario, email, token)
    return usuario


def _validar_datos_de_registro(datos: RegistroClienteEntrada) -> None:
    campos: dict[str, str] = {}
    if not datos.acepta_politica:
        campos["acepta_politica"] = "Debes aceptar la política de tratamiento de datos personales."
    if datos.fecha_nacimiento > date.today():
        campos["fecha_nacimiento"] = "La fecha de nacimiento no puede ser futura."
    if not cumple_politica_contrasena(datos.contrasena):
        campos["contrasena"] = MENSAJE_POLITICA_CONTRASENA
    if campos:
        raise DatosInvalidos(campos=campos)


def _campos_duplicados(
    db: Session,
    *,
    nombre_usuario: str,
    email: str,
    tipo_documento: str,
    numero_documento: str,
) -> dict[str, str]:
    """RF-04, SUP-18: el nombre de usuario es único global; correo y documento, por rol."""
    campos: dict[str, str] = {}
    if db.scalar(
        select(Usuario.id).where(func.lower(Usuario.nombre_usuario) == nombre_usuario.lower())
    ):
        campos["nombre_usuario"] = MENSAJES_DUPLICADO["nombre_usuario"]
    if db.scalar(select(Usuario.id).where(Usuario.rol == Rol.CLIENTE, Usuario.email == email)):
        campos["email"] = MENSAJES_DUPLICADO["email"]
    if db.scalar(
        select(Usuario.id).where(
            Usuario.rol == Rol.CLIENTE,
            Usuario.tipo_documento == tipo_documento,
            Usuario.numero_documento == numero_documento,
        )
    ):
        campos["numero_documento"] = MENSAJES_DUPLICADO["numero_documento"]
    return campos


def _campo_por_restriccion(exc: IntegrityError) -> dict[str, str]:
    restriccion = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    campo = _CAMPO_POR_RESTRICCION.get(restriccion or "")
    return {campo: MENSAJES_DUPLICADO[campo]} if campo else {}


def _crear_token_verificacion(db: Session, usuario_id: int, email: str) -> str:
    """Crea un token de un solo uso y devuelve el valor en claro para el enlace (SUP-19)."""
    token = secrets.token_urlsafe(32)
    db.add(
        TokenVerificacion(
            usuario_id=usuario_id,
            token_hash=hash_token(token),
            email=email,
            expira_en=datetime.now(UTC) + timedelta(hours=HORAS_VERIFICACION),
        )
    )
    db.flush()
    return token


def enviar_verificacion(usuario: Usuario, email: str, token: str) -> None:
    """Envía el enlace `/verificar-correo?token=…` (HU-02). Un fallo de SMTP no tumba el
    registro: queda en el log y el cliente puede pedir el reenvío."""
    enlace = f"{get_settings().frontend_url}/verificar-correo?token={token}"
    nombres = escape(usuario.nombres or usuario.nombre_usuario)
    texto = (
        f"Hola {usuario.nombres or usuario.nombre_usuario},\n\n"
        "Gracias por registrarte en AVIANCO. Confirma tu correo con este enlace; "
        f"vence en {HORAS_VERIFICACION} horas y sirve una sola vez:\n\n"
        f"{enlace}\n\n"
        "Si no creaste esta cuenta, ignora este mensaje.\n"
    )
    html = (
        f"<p>Hola {nombres},</p>"
        "<p>Gracias por registrarte en AVIANCO. Confirma tu correo con este enlace; "
        f"vence en {HORAS_VERIFICACION} horas y sirve una sola vez.</p>"
        f'<p><a href="{enlace}">Verificar mi correo</a></p>'
        "<p>Si no creaste esta cuenta, ignora este mensaje.</p>"
    )
    try:
        enviar_correo(email, "Confirma tu correo en AVIANCO", texto, html)
    except Exception:
        # Sin el correo en el log: es un dato personal (Ley 1581 de 2012).
        logger.exception("No se pudo enviar el correo de verificación al usuario %s", usuario.id)


# ---------- Verificación de correo (HU-02) ----------


def verificar_correo(db: Session, token: str) -> None:
    """Marca como verificado el correo del enlace (HU-02, RF-05).

    El token es de un solo uso y vence en 24 horas (SUP-19). Al usarlo se invalidan los
    demás tokens vigentes de la cuenta. Lanza EnlaceInvalido si no existe, venció, ya se usó
    o no corresponde al correo vigente.

    El intercambio de un correo pendiente (HU-07) se implementa con esa historia.
    """
    ahora = datetime.now(UTC)
    fila = db.scalar(
        select(TokenVerificacion)
        .where(TokenVerificacion.token_hash == hash_token(token))
        .with_for_update()
    )
    if fila is None or fila.usado_en is not None or fila.expira_en <= ahora:
        raise EnlaceInvalido()

    usuario = db.get(Usuario, fila.usuario_id)
    if usuario is None or usuario.email is None or usuario.email != fila.email:
        raise EnlaceInvalido()

    fila.usado_en = ahora
    usuario.email_verificado = True
    db.execute(
        update(TokenVerificacion)
        .where(
            TokenVerificacion.usuario_id == usuario.id,
            TokenVerificacion.id != fila.id,
            TokenVerificacion.usado_en.is_(None),
        )
        .values(usado_en=ahora)
    )
    db.commit()


def reenviar_verificacion(db: Session, usuario_id: int) -> None:
    """Envía un enlace nuevo e invalida los anteriores (HU-02).

    El destino es el correo vigente de la cuenta. Si ya está verificado no hay nada que
    reenviar y responde CorreoYaVerificado. El correo de un cambio de perfil (HU-07) se
    agregará con esa historia.
    """
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()

    email = usuario.email
    if email is None or usuario.email_verificado:
        raise CorreoYaVerificado()

    ahora = datetime.now(UTC)
    db.execute(
        update(TokenVerificacion)
        .where(
            TokenVerificacion.usuario_id == usuario.id,
            TokenVerificacion.usado_en.is_(None),
        )
        .values(usado_en=ahora)
    )
    token = _crear_token_verificacion(db, usuario.id, email)
    db.commit()

    enviar_verificacion(usuario, email, token)


# ---------- Restablecimiento de contraseña (HU-05) ----------


def solicitar_restablecimiento(db: Session, email: str) -> None:
    """Envía un enlace de restablecimiento por cada cuenta activa con ese correo (HU-05).

    RF-07: no revela si el correo está registrado. Si el mismo correo pertenece a un cliente
    y a un administrador (SUP-18) se envía un enlace por cada cuenta. El root nunca recibe
    enlace. Al pedir uno nuevo, los enlaces anteriores sin usar dejan de servir.
    """
    destinatario = email.strip().lower()
    ahora = datetime.now(UTC)
    cuentas = db.scalars(
        select(Usuario)
        .where(
            Usuario.email == destinatario,
            Usuario.rol.in_((Rol.CLIENTE, Rol.ADMIN)),
            Usuario.activo.is_(True),
        )
        .order_by(Usuario.id)
    ).all()

    enviados: list[tuple[Usuario, str, str]] = []
    for usuario in cuentas:
        correo_cuenta = usuario.email
        if correo_cuenta is None:  # lo garantiza el filtro de la consulta
            continue
        db.execute(
            update(TokenRestablecimiento)
            .where(
                TokenRestablecimiento.usuario_id == usuario.id,
                TokenRestablecimiento.usado_en.is_(None),
            )
            .values(usado_en=ahora)
        )
        token = _crear_token_restablecimiento(db, usuario.id, ahora)
        enviados.append((usuario, correo_cuenta, token))

    if enviados:
        db.commit()
        for usuario, correo_cuenta, token in enviados:
            enviar_restablecimiento(usuario, correo_cuenta, token)


def _crear_token_restablecimiento(db: Session, usuario_id: int, ahora: datetime) -> str:
    """Crea un token de un solo uso y devuelve el valor en claro para el enlace (SUP-19)."""
    token = secrets.token_urlsafe(32)
    db.add(
        TokenRestablecimiento(
            usuario_id=usuario_id,
            token_hash=hash_token(token),
            expira_en=ahora + timedelta(minutes=MINUTOS_RESTABLECIMIENTO),
        )
    )
    db.flush()
    return token


def enviar_restablecimiento(usuario: Usuario, email: str, token: str) -> None:
    """Envía el enlace `/restablecer-contrasena?token=…` (HU-05).

    El correo identifica la cuenta para que el titular distinga los enlaces cuando su correo
    pertenece a una cuenta de cliente y a una de administrador. Un fallo de SMTP no cambia la
    respuesta de la solicitud: queda en el log y el usuario puede pedir otro enlace.
    """
    tipo_cuenta = "administrador" if usuario.rol == Rol.ADMIN else "cliente"
    enlace = f"{get_settings().frontend_url}/restablecer-contrasena?token={token}"
    nombre = escape(usuario.nombres or usuario.nombre_usuario)
    nombre_usuario = escape(usuario.nombre_usuario)
    texto = (
        f"Hola {usuario.nombres or usuario.nombre_usuario},\n\n"
        f"Recibimos una solicitud para restablecer la contraseña de tu cuenta de "
        f"{tipo_cuenta} «{usuario.nombre_usuario}» en AVIANCO. Define una contraseña nueva "
        f"con este enlace; vence en {MINUTOS_RESTABLECIMIENTO} minutos y sirve una sola vez:\n\n"
        f"{enlace}\n\n"
        "Si no solicitaste el cambio, ignora este mensaje: tu contraseña actual sigue "
        "funcionando.\n"
    )
    html = (
        f"<p>Hola {nombre},</p>"
        f"<p>Recibimos una solicitud para restablecer la contraseña de tu cuenta de "
        f"{tipo_cuenta} «{nombre_usuario}» en AVIANCO. Define una contraseña nueva con este "
        f"enlace; vence en {MINUTOS_RESTABLECIMIENTO} minutos y sirve una sola vez.</p>"
        f'<p><a href="{enlace}">Restablecer mi contraseña</a></p>'
        "<p>Si no solicitaste el cambio, ignora este mensaje: tu contraseña actual sigue "
        "funcionando.</p>"
    )
    try:
        enviar_correo(
            email,
            f"Restablece la contraseña de tu cuenta de {tipo_cuenta} en AVIANCO",
            texto,
            html,
        )
    except Exception:
        # Sin el correo en el log: es un dato personal (Ley 1581 de 2012).
        logger.exception(
            "No se pudo enviar el correo de restablecimiento al usuario %s", usuario.id
        )


def confirmar_restablecimiento(
    db: Session,
    token: str,
    *,
    contrasena_nueva: str,
    confirmacion: str,
) -> None:
    """Define la contraseña nueva con el token del enlace (HU-05, RF-07).

    El token es de un solo uso y vence en 30 minutos (SUP-19). Se valida antes que la
    contraseña para que un enlace vencido o usado siempre responda EnlaceInvalido. Al
    confirmar se invalidan los demás tokens de la cuenta, la contraseña anterior deja de
    funcionar y se cierran todas las sesiones (se incrementa `version_sesion`).
    """
    ahora = datetime.now(UTC)
    fila = db.scalar(
        select(TokenRestablecimiento)
        .where(TokenRestablecimiento.token_hash == hash_token(token))
        .with_for_update()
    )
    if fila is None or fila.usado_en is not None or fila.expira_en <= ahora:
        raise EnlaceInvalido()

    usuario = db.get(Usuario, fila.usuario_id)
    if usuario is None or usuario.rol == Rol.ROOT or not usuario.activo:
        raise EnlaceInvalido()

    _validar_contrasena_nueva(contrasena_nueva, confirmacion)

    fila.usado_en = ahora
    usuario.password_hash = hash_contrasena(contrasena_nueva)
    usuario.version_sesion = (usuario.version_sesion or 0) + 1
    db.execute(
        update(TokenRestablecimiento)
        .where(
            TokenRestablecimiento.usuario_id == usuario.id,
            TokenRestablecimiento.id != fila.id,
            TokenRestablecimiento.usado_en.is_(None),
        )
        .values(usado_en=ahora)
    )
    db.commit()


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
