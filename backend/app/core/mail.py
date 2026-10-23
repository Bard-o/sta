"""Correo saliente por SMTP (Mailpit en desarrollo; bandeja en http://localhost:8025).

- `encolar_correo(db, ...)` (RNF-05, RNF-21; issue #5): guarda el correo en `cola_correos`
  dentro de la transacción de quien llama, sin hacer commit. Si esa transacción se revierte, el
  correo no sale. Es la forma recomendada para todo correo:

      from app.core.mail import encolar_correo

      encolar_correo(db, destinatario, asunto, texto, html)
      db.commit()  # el commit de siempre del service

- `enviar_correo(...)`: envío inmediato y síncrono, sin cola ni reintentos; si SMTP falla lanza
  la excepción de smtplib. Se conserva para los envíos que ya existen.

En los tests, la fixture `smtp_falso` (app/core/testing.py) reemplaza el servidor SMTP.
"""

import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import CorreoEnCola

TIMEOUT_SMTP = 10
PENDIENTE, ENVIADO, FALLIDO = "pendiente", "enviado", "fallido"


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
