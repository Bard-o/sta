"""Correo saliente por SMTP (Mailpit en desarrollo; bandeja en http://localhost:8025).

- `encolar_correo(db, ...)` (RNF-05, RNF-21; issue #5): guarda el correo en `cola_correos`
  dentro de la transacción de quien llama, sin hacer commit. Si esa transacción se revierte, el
  correo no sale. La tarea programada `core.enviar_correos` (cada minuto) lo envía en su
  siguiente vuelta, así que sale en menos de 5 minutos (HU-08), y si SMTP falla lo reintenta
  con espera creciente (1, 2, 4 y luego 5 minutos). Es la forma recomendada para todo correo:

      from app.core.mail import encolar_correo

      encolar_correo(db, destinatario, asunto, texto, html)
      db.commit()  # el commit de siempre del service

- Adjuntos (RF-39; issue #116): `adjuntos=[Adjunto("comprobante-K7Q2MX.pdf", "application/pdf",
  contenido)]`. El contenido se guarda con `app.core.archivos` bajo `correos/<uuid>` antes de
  agregar las filas, y `cola_correos_adjuntos` guarda solo la referencia. Cada intento de envío
  vuelve a leer el mismo archivo; tras un envío exitoso el archivo se borra (la fila queda).
  Un correo `fallido` conserva sus archivos. Si la transacción de quien encola se revierte, el
  correo no sale y el archivo queda huérfano en el volumen (no lo referencia ninguna fila).
  Límites: MAX_ADJUNTOS por correo y MAX_BYTES_ADJUNTOS en total.

- `enviar_correo(...)`: envío inmediato y síncrono, sin cola, reintentos ni adjuntos; si SMTP
  falla lanza la excepción de smtplib. Se conserva para los envíos que ya existen.

En los tests, la fixture `smtp_falso` (app/core/testing.py) reemplaza el servidor SMTP y
`archivos_dir` lleva los adjuntos a un directorio temporal.
"""

import contextlib
import logging
import re
import smtplib
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import archivos
from app.core.config import get_settings
from app.core.db import AdjuntoEnCola, CorreoEnCola
from app.core.errors import NoEncontrado
from app.core.planificador import registrar_tarea

logger = logging.getLogger(__name__)

NOMBRE_TAREA = "core.enviar_correos"
INTERVALO_ENVIO = timedelta(minutes=1)  # HU-08: sale como máximo 5 min después
ESPERA_BASE = timedelta(minutes=1)
ESPERA_MAXIMA = timedelta(minutes=5)  # RNF-21: ≤ 10 min tras volver el SMTP
MAX_INTENTOS = 15  # ~1 hora de reintentos
LOTE_POR_VUELTA = 1000
DURACION_MAXIMA_VUELTA = timedelta(seconds=20)  # no retrasa las demás tareas (RNF-18)
TIMEOUT_SMTP = 10
PENDIENTE, ENVIADO, FALLIDO = "pendiente", "enviado", "fallido"
MAX_ADJUNTOS = 10
# En base64 el correo crece un tercio: 10 MB quedan bajo el límite usual de 20-25 MB de SMTP.
MAX_BYTES_ADJUNTOS = 10 * 1024 * 1024
PREFIJO_ADJUNTOS = "correos"  # claves de app.core.archivos: correos/<uuid hex>
_LARGO_NOMBRE = 255
# tipo/subtipo en minúscula (RFC 6838); multipart y message no son adjuntos de bytes.
_TIPO_MIME = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}")
_TIPOS_NO_ADJUNTABLES = ("multipart/", "message/")
_LARGO_ERROR = 1000
# Errores de un correo en particular: los demás de la vuelta sí pueden salir.
_ERRORES_DEL_CORREO = (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError, ValueError)
_monotonico = time.monotonic  # los tests lo reemplazan para probar el tope de tiempo


@dataclass(frozen=True)
class Adjunto:
    """Archivo adjunto de un correo (RF-39; issue #116)."""

    nombre: str  # "comprobante-K7Q2MX.pdf"
    tipo_mime: str  # "application/pdf"
    contenido: bytes


def _construir_mensaje(
    destinatario: str,
    asunto: str,
    texto: str,
    html: str | None,
    adjuntos: Sequence[Adjunto] = (),
) -> EmailMessage:
    settings = get_settings()
    mensaje = EmailMessage()
    mensaje["From"] = settings.mail_from
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(texto)
    if html:
        mensaje.add_alternative(html, subtype="html")
    for adjunto in adjuntos:
        tipo, _, subtipo = adjunto.tipo_mime.partition("/")
        mensaje.add_attachment(
            adjunto.contenido, maintype=tipo, subtype=subtipo, filename=adjunto.nombre
        )
    return mensaje


def enviar_correo(destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
    """Envía un correo de inmediato (síncrono, sin reintentos). Para correos nuevos usa
    `encolar_correo` (RNF-05)."""
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SMTP) as smtp:
        smtp.send_message(_construir_mensaje(destinatario, asunto, texto, html))


def _validar_adjuntos(adjuntos: Sequence[Adjunto]) -> None:
    """ValueError (o TypeError si el contenido no son bytes) ante un adjunto inválido."""
    if len(adjuntos) > MAX_ADJUNTOS:
        raise ValueError(f"Un correo admite máximo {MAX_ADJUNTOS} adjuntos.")
    total = 0
    for adjunto in adjuntos:
        if not isinstance(adjunto.contenido, bytes | bytearray):
            raise TypeError(f"El contenido del adjunto {adjunto.nombre!r} debe ser bytes.")
        if not adjunto.contenido:
            raise ValueError(f"El adjunto {adjunto.nombre!r} está vacío.")
        if not adjunto.nombre.strip() or len(adjunto.nombre) > _LARGO_NOMBRE:
            raise ValueError(f"Nombre de adjunto inválido: {adjunto.nombre!r}")
        if not _TIPO_MIME.fullmatch(adjunto.tipo_mime) or adjunto.tipo_mime.startswith(
            _TIPOS_NO_ADJUNTABLES
        ):
            raise ValueError(f"Tipo MIME de adjunto inválido: {adjunto.tipo_mime!r}")
        total += len(adjunto.contenido)
    if total > MAX_BYTES_ADJUNTOS:
        raise ValueError(f"Los adjuntos de un correo suman máximo {MAX_BYTES_ADJUNTOS} bytes.")


def _borrar_archivos(claves: Sequence[str]) -> None:
    """Borra los archivos de los adjuntos; un fallo solo deja un aviso en los logs."""
    for clave in claves:
        try:
            archivos.borrar(clave)
        except OSError:
            logger.warning("No se pudo borrar el adjunto %s", clave, exc_info=True)


def _guardar_adjuntos(adjuntos: Sequence[Adjunto]) -> list[str]:
    """Guarda el contenido de cada adjunto y devuelve sus claves; si uno falla, borra los demás."""
    claves: list[str] = []
    try:
        for adjunto in adjuntos:
            clave = f"{PREFIJO_ADJUNTOS}/{uuid.uuid4().hex}"
            archivos.guardar(clave, bytes(adjunto.contenido))
            claves.append(clave)
    except BaseException:
        _borrar_archivos(claves)
        raise
    return claves


def encolar_correo(
    db: Session,
    destinatario: str,
    asunto: str,
    texto: str,
    html: str | None = None,
    adjuntos: Sequence[Adjunto] = (),
) -> int:
    """Guarda el correo en la cola dentro de la transacción de `db` y devuelve su id.

    No hace commit: el correo sale después del commit de quien llama y, si esa transacción se
    revierte, no sale (criterio 1 del issue #5). Un destinatario o asunto con saltos de línea, o
    un adjunto inválido (vacío, sin nombre, tipo MIME mal formado o por encima de los límites),
    lanza ValueError (error de programación).

    Los adjuntos se guardan con `app.core.archivos` antes de agregar las filas: ninguna fila
    referencia un archivo que no existe. Si la transacción se revierte después, el archivo queda
    huérfano en el volumen y nunca se envía (issue #116).
    """
    adjuntos = tuple(adjuntos)
    _validar_adjuntos(adjuntos)
    _construir_mensaje(destinatario, asunto, texto, html, adjuntos)  # valida los encabezados ahora
    claves = _guardar_adjuntos(adjuntos)
    try:
        correo = CorreoEnCola(
            destinatario=destinatario,
            asunto=asunto,
            texto=texto,
            html=html,
            estado=PENDIENTE,
            intentos=0,
            proximo_intento_en=datetime.now(UTC),
        )
        db.add(correo)
        db.flush()
        if adjuntos:
            db.add_all(
                AdjuntoEnCola(
                    correo_id=correo.id,
                    posicion=posicion,
                    nombre=adjunto.nombre,
                    tipo_mime=adjunto.tipo_mime,
                    clave=clave,
                    tamano=len(adjunto.contenido),
                )
                for posicion, (adjunto, clave) in enumerate(zip(adjuntos, claves, strict=True))
            )
            db.flush()
    except BaseException:
        _borrar_archivos(claves)
        raise
    return correo.id


def espera_para(intentos: int) -> timedelta:
    """Espera después del intento fallido número `intentos`: 1, 2, 4 y luego 5 minutos."""
    return min(ESPERA_BASE * 2 ** min(intentos - 1, 10), ESPERA_MAXIMA)


class _ConexionSmtp:
    """Una conexión SMTP por vuelta, abierta con el primer envío."""

    def __init__(self) -> None:
        self._smtp = None  # sin anotación: los tests reemplazan smtplib.SMTP

    def enviar(self, mensaje: EmailMessage) -> None:
        if self._smtp is None:
            settings = get_settings()
            self._smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SMTP)
        try:
            self._smtp.send_message(mensaje)
        except BaseException:
            self._soltar(por_error=True)
            raise

    def cerrar(self) -> None:
        self._soltar(por_error=False)

    def _soltar(self, *, por_error: bool) -> None:
        smtp, self._smtp = self._smtp, None
        if smtp is None:
            return
        with contextlib.suppress(smtplib.SMTPException, OSError):
            if por_error:
                smtp.close()
            else:
                smtp.quit()


def _adjuntos_de(db: Session, correo_id: int) -> list[AdjuntoEnCola]:
    return list(
        db.scalars(
            select(AdjuntoEnCola)
            .where(AdjuntoEnCola.correo_id == correo_id)
            .order_by(AdjuntoEnCola.posicion)
        )
    )


def _leer_adjunto(fila: AdjuntoEnCola) -> Adjunto:
    """Vuelve a leer el archivo del adjunto; ValueError si falta o cambió (error del correo)."""
    try:
        contenido = archivos.leer(fila.clave)
    except NoEncontrado:
        raise ValueError(f"Falta el archivo del adjunto {fila.clave}") from None
    if len(contenido) != fila.tamano:
        raise ValueError(f"El archivo del adjunto {fila.clave} no tiene el tamaño guardado")
    return Adjunto(fila.nombre, fila.tipo_mime, contenido)


def _anotar_fallo(correo: CorreoEnCola, exc: BaseException, ahora: datetime) -> None:
    correo.ultimo_error = f"{type(exc).__name__}: {exc}"[:_LARGO_ERROR]
    if correo.intentos >= MAX_INTENTOS:
        correo.estado = FALLIDO
        logger.error(
            "El correo %s falló definitivamente tras %s intentos: %s",
            correo.id,
            correo.intentos,
            correo.ultimo_error,
        )
        return
    espera = espera_para(correo.intentos)
    correo.proximo_intento_en = ahora + espera
    logger.warning(
        "No se pudo enviar el correo %s (intento %s de %s); se reintenta en %s s: %s",
        correo.id,
        correo.intentos,
        MAX_INTENTOS,
        int(espera.total_seconds()),
        correo.ultimo_error,
    )


def enviar_pendientes(db: Session, ahora: datetime) -> int:
    """Tarea `core.enviar_correos`: envía los correos pendientes cuya hora ya llegó.

    - Toma cada correo con SELECT ... FOR UPDATE SKIP LOCKED: otro proceso salta los tomados.
    - A diferencia de las tareas de los módulos, confirma después de cada correo: un correo
      entregado queda `enviado` aunque la vuelta falle después y nunca se reenvía (issue #5).
      Si el proceso muere entre que SMTP acepta y el commit, como máximo ese correo se reenvía.
    - Si falla el servidor (conexión, desconexión, tiempo de espera) anota el intento y corta
      la vuelta; si falla solo ese correo (destinatario rechazado, adjunto perdido) sigue con
      los demás.
    - Cada intento vuelve a leer los adjuntos del volumen; los borra solo después del commit
      que deja el correo `enviado` (issue #116).
    - Procesa como máximo LOTE_POR_VUELTA correos o DURACION_MAXIMA_VUELTA.

    Devuelve cuántos correos entregó.
    """
    enviados = 0
    inicio = _monotonico()
    conexion = _ConexionSmtp()
    try:
        for _ in range(LOTE_POR_VUELTA):
            if _monotonico() - inicio >= DURACION_MAXIMA_VUELTA.total_seconds():
                break
            correo = db.scalars(
                select(CorreoEnCola)
                .where(CorreoEnCola.estado == PENDIENTE, CorreoEnCola.proximo_intento_en <= ahora)
                .order_by(CorreoEnCola.proximo_intento_en, CorreoEnCola.id)
                .limit(1)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).first()
            if correo is None:
                break
            correo.intentos += 1
            filas = _adjuntos_de(db, correo.id)
            try:
                conexion.enviar(
                    _construir_mensaje(
                        correo.destinatario,
                        correo.asunto,
                        correo.texto,
                        correo.html,
                        [_leer_adjunto(fila) for fila in filas],
                    )
                )
            except (smtplib.SMTPException, OSError, ValueError) as exc:
                _anotar_fallo(correo, exc, ahora)
                db.commit()
                if isinstance(exc, _ERRORES_DEL_CORREO):
                    continue
                break
            claves = [fila.clave for fila in filas]
            correo.estado = ENVIADO
            correo.enviado_en = ahora
            db.commit()
            _borrar_archivos(claves)
            enviados += 1
    finally:
        conexion.cerrar()
    return enviados


registrar_tarea(NOMBRE_TAREA, enviar_pendientes, cada=INTERVALO_ENVIO)
