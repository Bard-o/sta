"""Envío de correo por SMTP (mailpit en desarrollo)."""

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


def enviar_correo(destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
    settings = get_settings()
    mensaje = EmailMessage()
    mensaje["From"] = settings.mail_from
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(texto)
    if html:
        mensaje.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.send_message(mensaje)
