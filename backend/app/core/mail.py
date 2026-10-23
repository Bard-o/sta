"""Correo saliente por SMTP (Mailpit en desarrollo; bandeja en http://localhost:8025).

- `encolar_correo(db, ...)` (RNF-05, RNF-21; issue #5): guarda el correo en `cola_correos`
  dentro de la transacción de quien llama, sin hacer commit. Si esa transacción se revierte, el
  correo no sale. La tarea programada `core.enviar_correos` (cada minuto) lo envía en su
  siguiente vuelta, así que sale en menos de 5 minutos (HU-08), y si SMTP falla lo reintenta
  con espera creciente (1, 2, 4 y luego 5 minutos). Es la forma recomendada para todo correo:

      from app.core.mail import encolar_correo

      encolar_correo(db, destinatario, asunto, texto, html)
      db.commit()  # el commit de siempre del service

- `enviar_correo(...)`: envío inmediato y síncrono, sin cola ni reintentos; si SMTP falla lanza
  la excepción de smtplib. Se conserva para los envíos que ya existen.

En los tests, la fixture `smtp_falso` (app/core/testing.py) reemplaza el servidor SMTP.
"""

import contextlib
import logging
import smtplib
import time
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import CorreoEnCola
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
_LARGO_ERROR = 1000
# Errores de un correo en particular: los demás de la vuelta sí pueden salir.
_ERRORES_DEL_CORREO = (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError, ValueError)
_monotonico = time.monotonic  # los tests lo reemplazan para probar el tope de tiempo


def _construir_mensaje(
    destinatario: str, asunto: str, texto: str, html: str | None
) -> EmailMessage:
    settings = get_settings()
    mensaje = EmailMessage()
    mensaje["From"] = settings.mail_from
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(texto)
    if html:
        mensaje.add_alternative(html, subtype="html")
    return mensaje


def enviar_correo(destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
    """Envía un correo de inmediato (síncrono, sin reintentos). Para correos nuevos usa
    `encolar_correo` (RNF-05)."""
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SMTP) as smtp:
        smtp.send_message(_construir_mensaje(destinatario, asunto, texto, html))


def encolar_correo(
    db: Session, destinatario: str, asunto: str, texto: str, html: str | None = None
) -> int:
    """Guarda el correo en la cola dentro de la transacción de `db` y devuelve su id.

    No hace commit: el correo sale después del commit de quien llama y, si esa transacción se
    revierte, no sale (criterio 1 del issue #5). Un destinatario o asunto con saltos de línea
    lanza ValueError (error de programación).
    """
    _construir_mensaje(destinatario, asunto, texto, html)  # valida los encabezados ahora
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
      la vuelta; si falla solo ese correo (destinatario rechazado) sigue con los demás.
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
            try:
                conexion.enviar(
                    _construir_mensaje(
                        correo.destinatario, correo.asunto, correo.texto, correo.html
                    )
                )
            except (smtplib.SMTPException, OSError, ValueError) as exc:
                _anotar_fallo(correo, exc, ahora)
                db.commit()
                if isinstance(exc, _ERRORES_DEL_CORREO):
                    continue
                break
            correo.estado = ENVIADO
            correo.enviado_en = ahora
            db.commit()
            enviados += 1
    finally:
        conexion.cerrar()
    return enviados


registrar_tarea(NOMBRE_TAREA, enviar_pendientes, cada=INTERVALO_ENVIO)
