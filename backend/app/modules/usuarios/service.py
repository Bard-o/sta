"""Interfaz pública del módulo usuarios. Otros módulos solo llaman a estas funciones."""

import hashlib
import logging
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html import escape
from typing import BinaryIO

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import archivos
from app.core.config import get_settings
from app.core.errors import (
    AppError,
    DatosInvalidos,
    DemasiadosIntentos,
    NoAutenticado,
    NoEncontrado,
)
from app.core.mail import enviar_correo
from app.core.security import (
    MENSAJE_POLITICA_CONTRASENA,
    Rol,
    cumple_politica_contrasena,
    hash_contrasena,
    verificar_contrasena,
)
from app.modules.auditoria import service as auditoria_service
from app.modules.reservas import service as reservas_service
from app.modules.usuarios.models import TokenRestablecimiento, TokenVerificacion, Usuario
from app.modules.usuarios.schemas import (
    AdministradorEntrada,
    AdministradorSalida,
    EstadoAdministrador,
    PerfilEntrada,
    PerfilSalida,
    RegistroAdministradorEntrada,
    RegistroClienteEntrada,
)

logger = logging.getLogger(__name__)

# SUP-19: el enlace de verificación de correo vence en 24 horas.
HORAS_VERIFICACION = 24
# SUP-19: el enlace de restablecimiento de contraseña vence en 30 minutos.
MINUTOS_RESTABLECIMIENTO = 30
# RF-07: la solicitud responde lo mismo exista o no el correo.
MENSAJE_RESTABLECIMIENTO = (
    "Si el correo está registrado, recibirás un enlace válido por 30 minutos."
)

# RNF-13: tras 5 intentos fallidos consecutivos la cuenta se bloquea 15 minutos.
MAX_INTENTOS_FALLIDOS = 5
MINUTOS_BLOQUEO = 15

# HU-01, HU-07: la imagen de perfil es JPG o PNG de máximo 2 MB (RF-03).
MAX_BYTES_IMAGEN = 2 * 1024 * 1024
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
FIRMA_JPEG = b"\xff\xd8\xff"
MENSAJE_IMAGEN_INVALIDA = "La imagen debe ser JPG o PNG."
MENSAJE_IMAGEN_GRANDE = "La imagen pesa más de 2 MB. Elige una más liviana."


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


class CorreoNoVerificado(AppError):
    """HU-08: sin el correo verificado no se puede suscribir a noticias."""

    status_code = 403
    codigo = "correo_no_verificado"
    mensaje = "Verifica tu correo para suscribirte a noticias."


class TiquetesActivos(AppError):
    """HU-09: el cliente tiene compras o reservas activas en vuelos futuros."""

    status_code = 409
    codigo = "tiquetes_activos"
    mensaje = "Tienes compras o reservas activas en vuelos futuros."


class EstadoInvalido(AppError):
    """HU-11: desactivar uno ya inactivo o reactivar uno que sigue activo."""

    status_code = 409
    codigo = "estado_invalido"
    mensaje = "El administrador no está en el estado necesario para esta acción."


class RegistroYaCompleto(AppError):
    """HU-12: el administrador ya completó su registro."""

    status_code = 409
    codigo = "registro_ya_completo"
    mensaje = "Tu registro ya está completo."


MENSAJES_DUPLICADO = {
    "nombre_usuario": "Ese nombre de usuario ya está en uso.",
    "email": "Ese correo ya está registrado en otra cuenta de cliente.",
    "numero_documento": "Ese número de documento ya está registrado en otra cuenta de cliente.",
}

# HU-12: documento y correo son únicos entre administradores (RF-04, SUP-18).
MENSAJES_DUPLICADO_ADMIN = {
    "email": "Ese correo ya está registrado en otra cuenta de administrador.",
    "numero_documento": (
        "Ese número de documento ya está registrado en otra cuenta de administrador."
    ),
}

# HU-07: el correo se comparte entre clientes y, por separado, entre administradores (SUP-18).
MENSAJE_EMAIL_DUPLICADO = "Ese correo ya está registrado en otra cuenta."

# Restricciones de la tabla usuarios que pueden saltar al registrar un cliente.
_CAMPO_POR_RESTRICCION = {
    "uq_usuarios_nombre_usuario": "nombre_usuario",
    "uq_usuarios_nombre_usuario_lower": "nombre_usuario",
    "uq_usuarios_rol_email": "email",
    "uq_usuarios_rol_documento": "numero_documento",
}


def _ahora_utc() -> datetime:
    """Reloj del módulo. Los tests lo sustituyen para controlar el bloqueo (RNF-13)."""
    return datetime.now(UTC)


def _bloqueo_vigente(usuario: Usuario, ahora: datetime) -> datetime | None:
    if usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > ahora:
        return usuario.bloqueado_hasta
    return None


def _reiniciar_intentos(usuario: Usuario) -> None:
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None


def _lanzar_demasiados_intentos(bloqueados: list[Usuario], ahora: datetime) -> None:
    """RNF-13: 429 con los segundos que faltan para que la cuenta vuelva a estar disponible."""
    espera = max(
        usuario.bloqueado_hasta for usuario in bloqueados if usuario.bloqueado_hasta is not None
    )
    segundos = max(1, math.ceil((espera - ahora).total_seconds()))
    minutos = max(1, math.ceil(segundos / 60))
    unidad = "minuto" if minutos == 1 else "minutos"
    raise DemasiadosIntentos(
        mensaje=f"Cuenta bloqueada. Intenta de nuevo en {minutos} {unidad}.",
        headers={"Retry-After": str(segundos)},
    )


def autenticar(db: Session, identificador: str, contrasena: str) -> Usuario:
    """Valida nombre de usuario (o correo) y contraseña. Lanza CredencialesInvalidas,
    CuentaInactiva o DemasiadosIntentos."""
    ahora = _ahora_utc()
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

    # Un bloqueo vencido se limpia y el contador vuelve a cero.
    for usuario in candidatos:
        if usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta <= ahora:
            _reiniciar_intentos(usuario)

    bloqueados = [u for u in candidatos if _bloqueo_vigente(u, ahora) is not None]
    if len(bloqueados) == len(candidatos):
        # El sexto intento se rechaza aunque la contraseña sea correcta (RNF-13).
        _lanzar_demasiados_intentos(bloqueados, ahora)

    # Un mismo correo puede tener una cuenta de cliente y otra de administrador (SUP-18).
    coincidencias = [u for u in candidatos if verificar_contrasena(contrasena, u.password_hash)]
    if coincidencias:
        desbloqueadas = [u for u in coincidencias if _bloqueo_vigente(u, ahora) is None]
        activas = [u for u in desbloqueadas if u.activo]
        if activas:
            usuario = activas[0]
            # Un login correcto reinicia el contador (RNF-13).
            _reiniciar_intentos(usuario)
            db.commit()
            return usuario
        db.commit()  # persiste la limpieza de bloqueos vencidos, si hubo
        if desbloqueadas:
            raise CuentaInactiva()
        _lanzar_demasiados_intentos(coincidencias, ahora)

    # Contraseña incorrecta: cuenta para todas las cuentas no bloqueadas que coinciden.
    for usuario in candidatos:
        if _bloqueo_vigente(usuario, ahora) is not None:
            continue
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= MAX_INTENTOS_FALLIDOS:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=MINUTOS_BLOQUEO)
    db.commit()
    raise CredencialesInvalidas()


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
    if _nombre_usuario_en_uso(db, nombre_usuario):
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


def _nombre_usuario_en_uso(db: Session, nombre_usuario: str) -> bool:
    """SUP-18: el nombre de usuario es único en todo el sistema, sin distinguir mayúsculas."""
    return (
        db.scalar(
            select(Usuario.id).where(
                func.lower(Usuario.nombre_usuario) == nombre_usuario.strip().lower()
            )
        )
        is not None
    )


def _campo_por_restriccion(
    exc: IntegrityError, mensajes: dict[str, str] | None = None
) -> dict[str, str]:
    mensajes = mensajes or MENSAJES_DUPLICADO
    restriccion = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    campo = _CAMPO_POR_RESTRICCION.get(restriccion or "")
    return {campo: mensajes[campo]} if campo in mensajes else {}


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


def _invalidar_tokens(db: Session, usuario_id: int, ahora: datetime) -> None:
    """Marca como usados todos los enlaces de verificación vigentes de la cuenta."""
    db.execute(
        update(TokenVerificacion)
        .where(
            TokenVerificacion.usuario_id == usuario_id,
            TokenVerificacion.usado_en.is_(None),
        )
        .values(usado_en=ahora)
    )


def enviar_verificacion(usuario: Usuario, email: str, token: str, *, cambio: bool = False) -> None:
    """Envía el enlace `/verificar-correo?token=…` (HU-02, HU-07). Un fallo de SMTP no tumba
    la operación: queda en el log y el usuario puede pedir el reenvío."""
    enlace = f"{get_settings().frontend_url}/verificar-correo?token={token}"
    nombre = usuario.nombres or usuario.nombre_usuario
    nombres = escape(nombre)
    if cambio:
        asunto = "Confirma tu nuevo correo en AVIANCO"
        texto = (
            f"Hola {nombre},\n\n"
            "Recibimos una solicitud para cambiar el correo de tu cuenta AVIANCO. "
            f"Confirma el correo nuevo con este enlace; vence en {HORAS_VERIFICACION} horas "
            "y sirve una sola vez. Mientras no lo confirmes, el correo anterior sigue siendo "
            "el de la cuenta:\n\n"
            f"{enlace}\n\n"
            "Si no solicitaste el cambio, ignora este mensaje.\n"
        )
        html = (
            f"<p>Hola {nombres},</p>"
            "<p>Recibimos una solicitud para cambiar el correo de tu cuenta AVIANCO. "
            f"Confirma el correo nuevo con este enlace; vence en {HORAS_VERIFICACION} horas "
            "y sirve una sola vez. Mientras no lo confirmes, el correo anterior sigue siendo "
            "el de la cuenta.</p>"
            f'<p><a href="{enlace}">Confirmar mi nuevo correo</a></p>'
            "<p>Si no solicitaste el cambio, ignora este mensaje.</p>"
        )
    else:
        asunto = "Confirma tu correo en AVIANCO"
        texto = (
            f"Hola {nombre},\n\n"
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
        enviar_correo(email, asunto, texto, html)
    except Exception:
        # Sin el correo en el log: es un dato personal (Ley 1581 de 2012).
        logger.exception("No se pudo enviar el correo de verificación al usuario %s", usuario.id)


# ---------- Verificación de correo (HU-02) ----------


def verificar_correo(db: Session, token: str) -> None:
    """Marca como verificado el correo del enlace (HU-02, RF-05).

    El token es de un solo uso y vence en 24 horas (SUP-19). Al usarlo se invalidan los
    demás tokens vigentes de la cuenta. Si el enlace es de un cambio de perfil (HU-07), el
    correo pendiente pasa a ser el de la cuenta. Lanza EnlaceInvalido si no existe, venció,
    ya se usó o no corresponde al correo vigente ni al pendiente.
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
    if usuario is None or usuario.email is None:
        raise EnlaceInvalido()

    if fila.email == usuario.email:
        pass
    elif fila.email == usuario.email_pendiente:
        usuario.email = fila.email
        usuario.email_pendiente = None
    else:
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
    try:
        db.commit()
    except IntegrityError as exc:
        # Carrera: otra cuenta tomó ese correo entre el PUT del perfil y la verificación.
        db.rollback()
        raise DatosDuplicados(campos={"email": MENSAJE_EMAIL_DUPLICADO}) from exc


def reenviar_verificacion(db: Session, usuario_id: int) -> None:
    """Envía un enlace nuevo e invalida los anteriores (HU-02, HU-07).

    El destino es el correo pendiente si hay un cambio de perfil sin verificar; si no, el
    correo vigente. Si el correo vigente ya está verificado y no hay pendiente, responde
    CorreoYaVerificado.
    """
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()

    email = usuario.email_pendiente or usuario.email
    if email is None or (usuario.email_pendiente is None and usuario.email_verificado):
        raise CorreoYaVerificado()

    ahora = datetime.now(UTC)
    _invalidar_tokens(db, usuario.id, ahora)
    token = _crear_token_verificacion(db, usuario.id, email)
    db.commit()

    enviar_verificacion(usuario, email, token, cambio=usuario.email_pendiente is not None)


# ---------- Perfil (HU-07) ----------


def _validar_datos_editables(datos: PerfilEntrada) -> None:
    """RF-08: la fecha de nacimiento no puede ser futura."""
    _validar_fecha_nacimiento(datos.fecha_nacimiento)


def _validar_fecha_nacimiento(fecha_nacimiento: date) -> None:
    """RF-03, HU-12: la fecha de nacimiento no puede ser futura."""
    if fecha_nacimiento > date.today():
        raise DatosInvalidos(
            campos={"fecha_nacimiento": "La fecha de nacimiento no puede ser futura."}
        )


def _email_en_uso(db: Session, email: str, rol: Rol, excluir_id: int) -> bool:
    """RF-04, SUP-18: el correo es único dentro de cada rol, también si está pendiente."""
    return (
        db.scalar(
            select(Usuario.id).where(
                Usuario.rol == rol,
                Usuario.id != excluir_id,
                or_(Usuario.email == email, Usuario.email_pendiente == email),
            )
        )
        is not None
    )


def _perfil_salida(usuario: Usuario) -> PerfilSalida:
    """Arma la respuesta del perfil. `NoEncontrado` si la cuenta aún no tiene sus datos.

    Un administrador con el registro incompleto (HU-12) no tiene perfil todavía; el bloqueo
    de `core` (HU-12) lo atiende antes de llegar aquí.
    """
    if (
        usuario.email is None
        or usuario.tipo_documento is None
        or usuario.numero_documento is None
        or usuario.nombres is None
        or usuario.apellidos is None
        or usuario.fecha_nacimiento is None
        or usuario.lugar_nacimiento is None
        or usuario.direccion_facturacion is None
        or usuario.genero is None
    ):
        raise NoEncontrado()

    return PerfilSalida(
        id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        rol=usuario.rol.value,
        tipo_documento=usuario.tipo_documento,
        numero_documento=usuario.numero_documento,
        nombres=usuario.nombres,
        apellidos=usuario.apellidos,
        fecha_nacimiento=usuario.fecha_nacimiento,
        lugar_nacimiento=usuario.lugar_nacimiento,
        direccion_facturacion=usuario.direccion_facturacion,
        genero=usuario.genero,
        email=usuario.email,
        email_verificado=usuario.email_verificado,
        email_pendiente=usuario.email_pendiente,
        telefono=usuario.telefono,
        # HU-07: la versión cambia en cada subida para vencer el caché del navegador.
        imagen_url=(
            f"/api/v1/usuarios/me/imagen?v={usuario.imagen_version}"
            if usuario.imagen_tipo is not None
            else None
        ),
        # HU-08, RF-09: el perfil refleja la suscripción vigente del cliente. El administrador
        # no se suscribe (el endpoint de suscripción es solo para clientes), así que es false.
        suscrito_noticias=usuario.suscrito_noticias if usuario.rol == Rol.CLIENTE else False,
    )


def obtener_perfil(db: Session, usuario_id: int) -> PerfilSalida:
    """Perfil del cliente o administrador de la sesión (HU-07)."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()
    return _perfil_salida(usuario)


def actualizar_perfil(db: Session, usuario_id: int, datos: PerfilEntrada) -> PerfilSalida:
    """Actualiza los datos editables del perfil (HU-07, RF-08).

    El documento y el nombre de usuario no se tocan porque no están en `PerfilEntrada`. Un
    correo distinto del vigente queda en `email_pendiente` y se envía el enlace de HU-02 al
    correo nuevo; el anterior sigue siendo el de la cuenta hasta verificarlo (SUP-42).
    """
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()

    _validar_datos_editables(datos)
    email = datos.email.strip().lower()
    token: str | None = None

    if email != usuario.email:
        if email != usuario.email_pendiente:
            if _email_en_uso(db, email, usuario.rol, usuario.id):
                raise DatosDuplicados(campos={"email": MENSAJE_EMAIL_DUPLICADO})
            usuario.email_pendiente = email
            _invalidar_tokens(db, usuario.id, datetime.now(UTC))
            token = _crear_token_verificacion(db, usuario.id, email)
    elif usuario.email_pendiente is not None:
        # Volvió a escribir el correo vigente: se descarta el cambio pendiente.
        usuario.email_pendiente = None
        _invalidar_tokens(db, usuario.id, datetime.now(UTC))

    usuario.nombres = datos.nombres.strip()
    usuario.apellidos = datos.apellidos.strip()
    usuario.fecha_nacimiento = datos.fecha_nacimiento
    usuario.lugar_nacimiento = datos.lugar_nacimiento.strip()
    usuario.direccion_facturacion = datos.direccion_facturacion.strip()
    usuario.genero = datos.genero
    usuario.telefono = datos.telefono.strip() if datos.telefono else None
    db.commit()

    if token is not None:
        enviar_verificacion(usuario, email, token, cambio=True)

    return _perfil_salida(usuario)


# ---------- Imagen de perfil (HU-01, HU-07) ----------


def _clave_imagen(usuario_id: int) -> str:
    """Clave del archivo en `core.archivos`; se arma con el id, nunca con texto del cliente."""
    return f"perfiles/{usuario_id}"


def _tipo_de_imagen(contenido: bytes) -> str | None:
    """Media type según la firma de los bytes, no la extensión ni el content-type del cliente."""
    if contenido.startswith(FIRMA_PNG):
        return "image/png"
    if contenido.startswith(FIRMA_JPEG):
        return "image/jpeg"
    return None


def subir_imagen(db: Session, usuario_id: int, archivo: BinaryIO) -> PerfilSalida:
    """Sube o reemplaza la imagen de perfil y devuelve el perfil actualizado (HU-01, HU-07).

    Solo acepta JPG o PNG de máximo 2 MB, validando el contenido y no la extensión; el error
    va en `campos.imagen`. El media type se deduce de la firma y la versión sube para que
    `imagen_url` cambie y el navegador no muestre la anterior desde su caché.
    """
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()
    # Un administrador con el registro incompleto (HU-12) todavía no tiene perfil.
    _perfil_salida(usuario)

    contenido = archivo.read(MAX_BYTES_IMAGEN + 1)
    if len(contenido) > MAX_BYTES_IMAGEN:
        raise DatosInvalidos(campos={"imagen": MENSAJE_IMAGEN_GRANDE})
    tipo = _tipo_de_imagen(contenido)
    if tipo is None:
        raise DatosInvalidos(campos={"imagen": MENSAJE_IMAGEN_INVALIDA})

    archivos.guardar(_clave_imagen(usuario.id), contenido)
    usuario.imagen_tipo = tipo
    usuario.imagen_version = (usuario.imagen_version or 0) + 1
    db.commit()
    return _perfil_salida(usuario)


def obtener_imagen(db: Session, usuario_id: int) -> tuple[bytes, str]:
    """Bytes y media type de la imagen de perfil; `NoEncontrado` si la cuenta no tiene (HU-07)."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()
    if usuario.imagen_tipo is None:
        raise NoEncontrado()
    return archivos.leer(_clave_imagen(usuario.id)), usuario.imagen_tipo


def borrar_imagen(db: Session, usuario_id: int) -> None:
    """Quita la imagen de perfil (HU-07). Es idempotente: sin imagen también responde 204."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()
    archivos.borrar(_clave_imagen(usuario.id))
    usuario.imagen_tipo = None
    db.commit()


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


# ---------- Desactivación de cuenta (HU-09) ----------


def bloqueos_de_desactivacion(db: Session, usuario_id: int) -> list[reservas_service.TiqueteActivo]:
    """Compras y reservas activas del cliente en vuelos futuros (HU-09, RF-10).

    La regla vive en reservas; esta función solo la expone para el aviso del perfil. En la
    iteración 1 todavía no hay ventas y la lista siempre sale vacía.
    """
    return reservas_service.tiquetes_activos_futuros_de_cliente(db, usuario_id)


def desactivar_cuenta(db: Session, usuario_id: int) -> None:
    """Desactiva la cuenta del cliente y cierra todas sus sesiones (HU-09, RF-10).

    Es un borrado lógico: los datos, el histórico y el saldo se conservan. Lanza
    TiquetesActivos si el cliente tiene compras o reservas activas en vuelos futuros.
    La cookie la borra el router.
    """
    if bloqueos_de_desactivacion(db, usuario_id):
        raise TiquetesActivos()

    # `activo` ya invalida la sesión en core/auth; `version_sesion` cierra además todas las
    # sesiones abiertas en otros dispositivos.
    db.execute(
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(activo=False, version_sesion=Usuario.version_sesion + 1)
    )
    db.commit()


def asegurar_root(db: Session, nombre_usuario: str, contrasena: str) -> bool:
    """Crea el único usuario root si no existe (RF-01). Devuelve True si lo creó."""
    existe = db.scalar(select(Usuario.id).where(Usuario.rol == Rol.ROOT).limit(1))
    if existe is not None:
        return False
    crear_usuario(db, nombre_usuario=nombre_usuario, contrasena=contrasena, rol=Rol.ROOT)
    return True


# ---------- Administradores (HU-10, HU-11) ----------


def _estado_administrador(usuario: Usuario) -> EstadoAdministrador:
    """Estado que ve el root (HU-11).

    Una cuenta desactivada se muestra como inactiva y guarda en sus banderas el estado al que
    vuelve cuando se reactive: activo o registro incompleto (HU-11, HU-12).
    """
    if not usuario.activo:
        return "inactivo"
    if not usuario.registro_completo:
        return "registro_incompleto"
    return "activo"


def _administrador_salida(usuario: Usuario) -> AdministradorSalida:
    return AdministradorSalida(
        id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        nombres=usuario.nombres,
        apellidos=usuario.apellidos,
        estado=_estado_administrador(usuario),
        creado_en=usuario.creado_en,
    )


def _detalle_administrador(usuario: Usuario) -> dict[str, object]:
    """Copia para la auditoría, sin la contraseña (RF-26, RNF-08)."""
    return {
        "nombre_usuario": usuario.nombre_usuario,
        "rol": usuario.rol.value,
        "estado": _estado_administrador(usuario),
    }


def crear_administrador(
    db: Session, datos: AdministradorEntrada, *, usuario_id: int
) -> AdministradorSalida:
    """HU-10, RF-02: el root crea un administrador con una contraseña temporal.

    Nace activo y con el registro incompleto: en su primer ingreso solo puede completar sus
    datos y cambiar la contraseña (HU-12). La creación y la auditoría entran en la misma
    transacción (RF-26, RNF-17). Lanza DatosInvalidos o DatosDuplicados.
    """
    nombre_usuario = datos.nombre_usuario.strip()
    if not cumple_politica_contrasena(datos.contrasena_temporal):
        raise DatosInvalidos(campos={"contrasena_temporal": MENSAJE_POLITICA_CONTRASENA})
    if _nombre_usuario_en_uso(db, nombre_usuario):
        raise DatosDuplicados(campos={"nombre_usuario": MENSAJES_DUPLICADO["nombre_usuario"]})

    # RF-01: el rol no se elige en el cuerpo; este endpoint nunca crea otro root.
    administrador = Usuario(
        nombre_usuario=nombre_usuario,
        email=None,
        email_verificado=False,
        password_hash=hash_contrasena(datos.contrasena_temporal),
        rol=Rol.ADMIN,
        registro_completo=False,
        activo=True,
    )
    db.add(administrador)
    try:
        db.flush()  # asigna el id antes de auditar
        auditoria_service.registrar(
            db,
            usuario_id=usuario_id,
            accion="administrador.crear",
            entidad="usuario",
            entidad_id=administrador.id,
            despues=_detalle_administrador(administrador),
        )
        db.commit()
    except IntegrityError as exc:
        # Carrera entre la verificación anterior y el commit: la restricción única decide.
        db.rollback()
        if _nombre_usuario_en_uso(db, nombre_usuario):
            raise DatosDuplicados(
                campos={"nombre_usuario": MENSAJES_DUPLICADO["nombre_usuario"]}
            ) from exc
        raise
    except Exception:
        # RNF-17: si falla la auditoría no queda el administrador.
        db.rollback()
        raise

    return _administrador_salida(administrador)


def _administrador_para_cambio(db: Session, admin_id: int) -> Usuario:
    """Administrador que el root va a desactivar o reactivar (HU-11).

    Bloquea la fila hasta el commit para que dos peticiones simultáneas no cambien el estado
    dos veces ni dejen dos registros de auditoría. Un id que no es de un administrador
    (inexistente, root o cliente) responde NoEncontrado, como el contrato.
    """
    administrador = db.scalar(
        select(Usuario).where(Usuario.id == admin_id, Usuario.rol == Rol.ADMIN).with_for_update()
    )
    if administrador is None:
        raise NoEncontrado("El administrador no existe.")
    return administrador


def desactivar_administrador(db: Session, admin_id: int, *, usuario_id: int) -> AdministradorSalida:
    """HU-11, RF-02: desactiva un administrador (borrado lógico) y cierra sus sesiones.

    Conserva los datos y el estado al que vuelve cuando se reactive (`registro_completo` decide
    si vuelve como activo o como registro incompleto). La desactivación y su auditoría entran
    en la misma transacción (RF-26, RNF-17). Lanza NoEncontrado o EstadoInvalido.
    """
    administrador = _administrador_para_cambio(db, admin_id)
    if not administrador.activo:
        raise EstadoInvalido("El administrador ya está inactivo.")

    antes = _detalle_administrador(administrador)
    administrador.activo = False
    # Cierra todas las sesiones abiertas del administrador en cualquier dispositivo.
    administrador.version_sesion = (administrador.version_sesion or 0) + 1
    try:
        auditoria_service.registrar(
            db,
            usuario_id=usuario_id,
            accion="administrador.desactivar",
            entidad="usuario",
            entidad_id=administrador.id,
            antes=antes,
            despues=_detalle_administrador(administrador),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _administrador_salida(administrador)


def reactivar_administrador(db: Session, admin_id: int, *, usuario_id: int) -> AdministradorSalida:
    """HU-11, RF-02: reactiva un administrador desactivado con su estado anterior.

    `registro_completo` se conservó al desactivar, así que vuelve como `activo` o como
    `registro_incompleto`. La reactivación y su auditoría entran en la misma transacción
    (RF-26, RNF-17). Lanza NoEncontrado o EstadoInvalido.
    """
    administrador = _administrador_para_cambio(db, admin_id)
    if administrador.activo:
        raise EstadoInvalido("El administrador ya está activo.")

    antes = _detalle_administrador(administrador)
    administrador.activo = True
    try:
        auditoria_service.registrar(
            db,
            usuario_id=usuario_id,
            accion="administrador.reactivar",
            entidad="usuario",
            entidad_id=administrador.id,
            antes=antes,
            despues=_detalle_administrador(administrador),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _administrador_salida(administrador)


def _campos_duplicados_administrador(
    db: Session,
    *,
    email: str,
    tipo_documento: str,
    numero_documento: str,
    excluir_id: int,
) -> dict[str, str]:
    """RF-04, SUP-18: correo y documento son únicos entre administradores.

    El correo también se compara contra el `email_pendiente` de otro administrador (HU-07)
    para no ocupar un cambio que está esperando verificación.
    """
    campos: dict[str, str] = {}
    if _email_en_uso(db, email, Rol.ADMIN, excluir_id):
        campos["email"] = MENSAJES_DUPLICADO_ADMIN["email"]
    documento_en_uso = db.scalar(
        select(Usuario.id).where(
            Usuario.rol == Rol.ADMIN,
            Usuario.id != excluir_id,
            Usuario.tipo_documento == tipo_documento,
            Usuario.numero_documento == numero_documento,
        )
    )
    if documento_en_uso is not None:
        campos["numero_documento"] = MENSAJES_DUPLICADO_ADMIN["numero_documento"]
    return campos


def completar_registro_administrador(
    db: Session, datos: RegistroAdministradorEntrada, *, usuario_id: int
) -> Usuario:
    """HU-12, RF-02 a RF-04: completa los datos del administrador y cambia la temporal.

    Mientras `registro_completo` sea falso, `core` solo deja llegar a este endpoint. El correo
    no pasa por la verificación de HU-02: queda verificado. La sesión actual sigue abierta, así
    que no se incrementa `version_sesion`. Las reglas sin estado se validan antes de comprobar
    la contraseña temporal, igual que en HU-06. Lanza RegistroYaCompleto, DatosInvalidos,
    ContrasenaActualIncorrecta o DatosDuplicados.
    """
    usuario = db.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update())
    if usuario is None:
        raise NoAutenticado()

    # HU-12: completar dos veces responde 409 aunque el cuerpo sea válido.
    if usuario.registro_completo:
        raise RegistroYaCompleto()

    _validar_fecha_nacimiento(datos.fecha_nacimiento)
    _validar_contrasena_nueva(datos.contrasena_nueva, datos.confirmacion)

    if not verificar_contrasena(datos.contrasena_temporal, usuario.password_hash):
        mensaje = "La contraseña temporal no es correcta."
        raise ContrasenaActualIncorrecta(mensaje, campos={"contrasena_temporal": mensaje})

    email = datos.email.strip().lower()
    campos = _campos_duplicados_administrador(
        db,
        email=email,
        tipo_documento=datos.tipo_documento,
        numero_documento=datos.numero_documento,
        excluir_id=usuario.id,
    )
    if campos:
        raise DatosDuplicados(campos=campos)

    usuario.email = email
    usuario.email_pendiente = None
    # El correo del administrador no se verifica en la iteración 1 (HU-12).
    usuario.email_verificado = True
    usuario.tipo_documento = datos.tipo_documento
    usuario.numero_documento = datos.numero_documento
    usuario.nombres = datos.nombres.strip()
    usuario.apellidos = datos.apellidos.strip()
    usuario.fecha_nacimiento = datos.fecha_nacimiento
    usuario.lugar_nacimiento = datos.lugar_nacimiento.strip()
    usuario.direccion_facturacion = datos.direccion_facturacion.strip()
    usuario.genero = datos.genero
    usuario.telefono = datos.telefono.strip() if datos.telefono else None
    usuario.password_hash = hash_contrasena(datos.contrasena_nueva)
    usuario.registro_completo = True

    try:
        db.commit()
    except IntegrityError as exc:
        # Carrera entre la verificación anterior y el commit: la restricción única decide.
        db.rollback()
        campos = _campos_duplicados_administrador(
            db,
            email=email,
            tipo_documento=datos.tipo_documento,
            numero_documento=datos.numero_documento,
            excluir_id=usuario_id,
        ) or _campo_por_restriccion(exc, MENSAJES_DUPLICADO_ADMIN)
        raise DatosDuplicados(campos=campos or None) from exc

    return usuario


def listar_administradores(db: Session) -> list[AdministradorSalida]:
    """Administradores con su estado, del más reciente al más antiguo (HU-10, HU-11)."""
    administradores = db.scalars(
        select(Usuario)
        .where(Usuario.rol == Rol.ADMIN)
        .order_by(Usuario.creado_en.desc(), Usuario.id.desc())
    )
    return [_administrador_salida(administrador) for administrador in administradores]


@dataclass(frozen=True)
class SuscriptorNoticias:
    usuario_id: int
    email: str
    nombres: str
    # Va en el enlace «cancelar suscripción» del correo: POST /usuarios/suscripcion/baja.
    token_baja: str


def _nuevo_token_baja() -> str:
    """Token del enlace de baja (HU-08): no vence y solo permite cancelar la suscripción."""
    return secrets.token_urlsafe(32)


def cambiar_suscripcion(db: Session, usuario_id: int, *, noticias: bool) -> bool:
    """Suscribe o da de baja al cliente del correo de noticias (HU-08, RF-09).

    Suscribirse exige el correo verificado; darse de baja siempre se permite. El token de
    baja se crea con la primera suscripción y no se rota: los enlaces de correos anteriores
    siguen sirviendo. El cambio aplica desde el siguiente envío.
    """
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoAutenticado()
    if noticias and not usuario.email_verificado:
        raise CorreoNoVerificado()

    if noticias and usuario.token_baja is None:
        usuario.token_baja = _nuevo_token_baja()
    usuario.suscrito_noticias = noticias
    db.commit()
    return usuario.suscrito_noticias


def dar_baja_con_token(db: Session, token: str) -> None:
    """Da de baja al cliente con el token del enlace del correo (HU-08, RF-56).

    No exige sesión y el token no vence. Un token inexistente responde EnlaceInvalido. Es
    idempotente: volver a abrir el enlace de una cuenta ya dada de baja también responde 204.
    """
    usuario = db.scalar(select(Usuario).where(Usuario.token_baja == token).with_for_update())
    if usuario is None:
        raise EnlaceInvalido()

    usuario.suscrito_noticias = False
    db.commit()


def suscriptores_noticias(db: Session) -> list[SuscriptorNoticias]:
    """Clientes activos, con el correo verificado y suscritos a noticias (RF-09, RF-56).

    La usa noticias para enviar el correo de cada noticia nueva. No hace commit: se ejecuta
    dentro de la transacción de quien llama. `nombres` cae al nombre de usuario si faltara.
    """
    usuarios = db.scalars(
        select(Usuario)
        .where(
            Usuario.rol == Rol.CLIENTE,
            Usuario.activo.is_(True),
            Usuario.email_verificado.is_(True),
            Usuario.suscrito_noticias.is_(True),
            Usuario.email.is_not(None),
            # Invariante: toda suscripción activa nace con token de baja.
            Usuario.token_baja.is_not(None),
        )
        .order_by(Usuario.id)
    ).all()
    return [
        SuscriptorNoticias(
            usuario_id=usuario.id,
            email=usuario.email,
            nombres=usuario.nombres or usuario.nombre_usuario,
            token_baja=usuario.token_baja,
        )
        for usuario in usuarios
    ]
