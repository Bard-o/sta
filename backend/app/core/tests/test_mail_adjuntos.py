"""Pruebas de los adjuntos de la cola de correos (issue #116: RF-39, RNF-05, RNF-21)."""

import email
import http.client
import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from pathlib import Path

import pytest
from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import archivos
from app.core import mail as modulo_mail
from app.core.config import get_settings
from app.core.db import AdjuntoEnCola, CorreoEnCola
from app.core.errors import NoEncontrado
from app.core.mail import (
    ENVIADO,
    FALLIDO,
    MAX_INTENTOS,
    PENDIENTE,
    Adjunto,
    encolar_correo,
    enviar_pendientes,
)
from app.core.testing import SmtpFalso

DESTINO = "laura@correo.test"
NOMBRE_PDF = "comprobante-K7Q2MX.pdf"


def _pdf() -> bytes:
    """Un PDF real hecho con fpdf2, la librería de PDF en Python puro que agrega el issue."""
    documento = FPDF()
    documento.add_page()
    documento.set_font("Helvetica", size=14)
    documento.cell(text="Comprobante K7Q2MX: Bogotá - Medellín, $ 800.000")
    return bytes(documento.output())


def _adjunto_pdf(contenido: bytes | None = None) -> Adjunto:
    return Adjunto(NOMBRE_PDF, "application/pdf", contenido or _pdf())


def _despues() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=1)


def _correos(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def _filas_adjuntos(db: Session) -> list[AdjuntoEnCola]:
    return list(db.scalars(select(AdjuntoEnCola).order_by(AdjuntoEnCola.id)))


def _por_el_cable(mensaje: EmailMessage) -> EmailMessage:
    """El mensaje tal como lo recibe el servidor: serializado y vuelto a leer."""
    recibido = email.message_from_bytes(mensaje.as_bytes(), policy=policy.default)
    assert isinstance(recibido, EmailMessage)
    return recibido


def _adjuntos_del_mensaje(mensaje: EmailMessage) -> list[tuple[str | None, str, bytes]]:
    return [
        (parte.get_filename(), parte.get_content_type(), parte.get_content())
        for parte in _por_el_cable(mensaje).iter_attachments()
    ]


def test_encolar_guarda_el_adjunto_en_archivos_y_la_cola_solo_la_referencia(db: Session):
    """Issue #116, contrato: el contenido va a core/archivos y la cola guarda la referencia."""
    pdf = _pdf()
    correo_id = encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[_adjunto_pdf(pdf)])
    (fila,) = _filas_adjuntos(db)
    assert (fila.correo_id, fila.posicion, fila.nombre, fila.tipo_mime, fila.tamano) == (
        correo_id,
        0,
        NOMBRE_PDF,
        "application/pdf",
        len(pdf),
    )
    assert re.fullmatch(r"correos/[0-9a-f]{32}", fila.clave)
    assert archivos.leer(fila.clave) == pdf


def test_un_correo_con_pdf_adjunto_sale_con_el_archivo_intacto(db: Session, smtp_falso: SmtpFalso):
    """Issue #116 criterio 1, RF-39: el PDF sale adjunto, byte a byte igual, junto al HTML."""
    pdf = _pdf()
    binario = Adjunto("datos.bin", "application/octet-stream", bytes(range(256)))
    encolar_correo(
        db, DESTINO, "Tu compra", "Hola Laura", "<p>Hola Laura</p>", [_adjunto_pdf(pdf), binario]
    )
    db.commit()
    assert enviar_pendientes(db, _despues()) == 1
    (mensaje,) = smtp_falso.enviados
    assert mensaje.get_content_type() == "multipart/mixed"
    assert mensaje.get_body(("html",)) is not None
    assert _adjuntos_del_mensaje(mensaje) == [
        (NOMBRE_PDF, "application/pdf", pdf),
        ("datos.bin", "application/octet-stream", bytes(range(256))),
    ]


def test_tras_el_envio_se_borra_el_archivo_y_queda_la_fila(db: Session, smtp_falso: SmtpFalso):
    """Issue #116: un adjunto entregado no ocupa el volumen; la fila queda como registro."""
    encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[_adjunto_pdf()])
    db.commit()
    (fila,) = _filas_adjuntos(db)
    assert enviar_pendientes(db, _despues()) == 1
    assert _correos(db)[0].estado == ENVIADO
    assert _filas_adjuntos(db) == [fila]
    with pytest.raises(NoEncontrado):
        archivos.leer(fila.clave)


def test_los_reintentos_reenvian_el_mismo_adjunto(db: Session, smtp_falso: SmtpFalso):
    """Issue #116 criterio 2, RNF-21: si SMTP falla, el reintento envía el mismo PDF."""
    pdf = _pdf()
    encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[_adjunto_pdf(pdf)])
    db.commit()
    (correo,) = _correos(db)
    (fila,) = _filas_adjuntos(db)
    t0 = _despues()

    smtp_falso.sin_conexion = True
    assert enviar_pendientes(db, t0) == 0
    db.refresh(correo)
    assert (correo.estado, correo.intentos) == (PENDIENTE, 1)
    assert archivos.leer(fila.clave) == pdf  # el intento fallido no borra el archivo

    smtp_falso.sin_conexion = False
    assert enviar_pendientes(db, correo.proximo_intento_en) == 1
    (mensaje,) = smtp_falso.enviados
    assert _adjuntos_del_mensaje(mensaje) == [(NOMBRE_PDF, "application/pdf", pdf)]


def test_un_destinatario_rechazado_reintenta_con_el_mismo_adjunto(
    db: Session, smtp_falso: SmtpFalso
):
    """Issue #116 criterio 2, RNF-21: tras un rechazo del correo, el reintento lleva el PDF."""
    pdf = _pdf()
    encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[_adjunto_pdf(pdf)])
    db.commit()
    (correo,) = _correos(db)
    smtp_falso.rechazados.add(DESTINO)
    assert enviar_pendientes(db, _despues()) == 0
    db.refresh(correo)
    smtp_falso.rechazados.clear()
    assert enviar_pendientes(db, correo.proximo_intento_en) == 1
    (mensaje,) = smtp_falso.enviados
    assert _adjuntos_del_mensaje(mensaje) == [(NOMBRE_PDF, "application/pdf", pdf)]


def test_un_correo_fallido_conserva_su_adjunto(db: Session, smtp_falso: SmtpFalso):
    """Issue #116, RNF-21: tras agotar los reintentos el archivo queda para reenviarlo a mano."""
    pdf = _pdf()
    encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[_adjunto_pdf(pdf)])
    db.commit()
    (correo,) = _correos(db)
    (fila,) = _filas_adjuntos(db)
    smtp_falso.sin_conexion = True
    ahora = _despues()
    for _ in range(MAX_INTENTOS):
        enviar_pendientes(db, ahora)
        db.refresh(correo)
        ahora = correo.proximo_intento_en
    assert correo.estado == FALLIDO
    assert archivos.leer(fila.clave) == pdf


def test_si_la_transaccion_se_revierte_el_correo_con_adjunto_no_sale(
    db: Session, smtp_falso: SmtpFalso
):
    """Issue #116 criterio 3: si quien encola revierte, no queda correo ni adjunto en la cola."""
    encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[_adjunto_pdf()])
    db.rollback()
    # El PDF queda huérfano en el volumen: ninguna fila lo referencia y nunca se envía.
    assert _correos(db) == []
    assert _filas_adjuntos(db) == []
    assert enviar_pendientes(db, _despues()) == 0
    assert smtp_falso.enviados == []


def test_si_falta_el_archivo_el_correo_falla_sin_detener_la_cola(
    db: Session, smtp_falso: SmtpFalso
):
    """Issue #116, RNF-21: un adjunto perdido es un error de ese correo; los demás salen."""
    encolar_correo(db, DESTINO, "Con adjunto", "Texto", adjuntos=[_adjunto_pdf()])
    encolar_correo(db, DESTINO, "Sin adjunto", "Texto")
    db.commit()
    (fila,) = _filas_adjuntos(db)
    archivos.borrar(fila.clave)
    assert enviar_pendientes(db, _despues()) == 1
    con_adjunto, sin_adjunto = _correos(db)
    assert sin_adjunto.estado == ENVIADO
    assert (con_adjunto.estado, con_adjunto.intentos) == (PENDIENTE, 1)
    assert "Falta el archivo del adjunto" in (con_adjunto.ultimo_error or "")
    assert [m["Subject"] for m in smtp_falso.enviados] == ["Sin adjunto"]


def test_un_correo_sin_adjuntos_funciona_igual_que_antes(
    db: Session, smtp_falso: SmtpFalso, archivos_dir: Path
):
    """Issue #116 criterio 4: sin adjuntos no se escribe ningún archivo y el mensaje no cambia."""
    encolar_correo(db, DESTINO, "Bienvenida", "Hola Laura", "<p>Hola Laura</p>")
    db.commit()
    assert _filas_adjuntos(db) == []
    assert not archivos_dir.exists()
    assert enviar_pendientes(db, _despues()) == 1
    (mensaje,) = smtp_falso.enviados
    assert mensaje.get_content_type() == "multipart/alternative"
    assert list(mensaje.iter_attachments()) == []
    assert _correos(db)[0].estado == ENVIADO


@pytest.mark.parametrize(
    ("adjunto", "error"),
    [
        (Adjunto("", "application/pdf", b"%PDF"), ValueError),
        (Adjunto("a\nBcc: x@y.pdf", "application/pdf", b"%PDF"), ValueError),
        (Adjunto("x" * 256, "application/pdf", b"%PDF"), ValueError),
        (Adjunto(NOMBRE_PDF, "pdf", b"%PDF"), ValueError),
        (Adjunto(NOMBRE_PDF, "Application/PDF", b"%PDF"), ValueError),
        (Adjunto(NOMBRE_PDF, "multipart/mixed", b"%PDF"), ValueError),
        (Adjunto(NOMBRE_PDF, "application/pdf", b""), ValueError),
        (Adjunto(NOMBRE_PDF, "application/pdf", "%PDF"), TypeError),
    ],
    ids=[
        "nombre_vacio",
        "nombre_con_salto_de_linea",
        "nombre_largo",
        "tipo_sin_subtipo",
        "tipo_en_mayusculas",
        "tipo_multipart",
        "contenido_vacio",
        "contenido_texto",
    ],
)
def test_encolar_rechaza_un_adjunto_invalido_sin_dejar_nada(
    db: Session, archivos_dir: Path, adjunto: Adjunto, error: type[Exception]
):
    """Issue #116: un adjunto inválido es un error de programación y no deja filas ni archivos."""
    with pytest.raises(error):
        encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[adjunto])
    assert _correos(db) == []
    assert not archivos_dir.exists()


def test_encolar_rechaza_adjuntos_por_encima_de_los_limites(
    db: Session, monkeypatch: pytest.MonkeyPatch
):
    """Issue #116: un correo admite MAX_ADJUNTOS adjuntos y MAX_BYTES_ADJUNTOS en total."""
    monkeypatch.setattr(modulo_mail, "MAX_BYTES_ADJUNTOS", 10)
    monkeypatch.setattr(modulo_mail, "MAX_ADJUNTOS", 2)
    pequeno = Adjunto("a.txt", "text/plain", b"12345")
    encolar_correo(db, DESTINO, "Justo", "Texto", adjuntos=[pequeno, pequeno])
    with pytest.raises(ValueError):
        encolar_correo(db, DESTINO, "Muchos", "Texto", adjuntos=[pequeno] * 3)
    with pytest.raises(ValueError):
        encolar_correo(
            db, DESTINO, "Grande", "Texto", adjuntos=[Adjunto("b.txt", "text/plain", b"x" * 11)]
        )
    assert [correo.asunto for correo in _correos(db)] == ["Justo"]


def test_si_falla_guardar_un_adjunto_no_queda_nada(
    db: Session, archivos_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Issue #116: si el volumen falla a mitad de los adjuntos, no queda correo ni archivo."""
    guardar_real = archivos.guardar
    llamadas = []

    def guardar_que_falla_la_segunda_vez(clave: str, contenido: bytes) -> None:
        llamadas.append(clave)
        if len(llamadas) == 2:
            raise OSError("disco lleno")
        guardar_real(clave, contenido)

    monkeypatch.setattr(archivos, "guardar", guardar_que_falla_la_segunda_vez)
    with pytest.raises(OSError):
        encolar_correo(db, DESTINO, "Tu compra", "Texto", adjuntos=[_adjunto_pdf(), _adjunto_pdf()])
    assert _correos(db) == []
    assert [ruta for ruta in archivos_dir.rglob("*") if ruta.is_file()] == []


def _mailpit(ruta: str) -> bytes:
    conexion = http.client.HTTPConnection(get_settings().smtp_host, 8025, timeout=5)
    try:
        conexion.request("GET", ruta)
        return conexion.getresponse().read()
    finally:
        conexion.close()


def _id_en_mailpit(asunto: str) -> str | None:
    mensajes = json.loads(_mailpit("/api/v1/messages?limit=100"))["messages"]
    return next((m["ID"] for m in mensajes if m["Subject"] == asunto), None)


def test_en_desarrollo_el_pdf_adjunto_llega_intacto_a_mailpit(db: Session):
    """Issue #116 criterio 1, RF-39: el PDF llega a la bandeja de Mailpit byte a byte igual."""
    pdf = _pdf()
    asunto = f"Prueba de adjunto {uuid.uuid4()}"
    encolar_correo(db, DESTINO, asunto, "Adjunto el comprobante", adjuntos=[_adjunto_pdf(pdf)])
    db.commit()
    assert enviar_pendientes(db, _despues()) == 1
    limite = time.monotonic() + 10
    while (mensaje_id := _id_en_mailpit(asunto)) is None:
        if time.monotonic() > limite:
            pytest.fail("El correo no apareció en Mailpit (http://localhost:8025) en 10 segundos.")
        time.sleep(0.5)
    (adjunto,) = json.loads(_mailpit(f"/api/v1/message/{mensaje_id}"))["Attachments"]
    assert (adjunto["FileName"], adjunto["ContentType"]) == (NOMBRE_PDF, "application/pdf")
    assert _mailpit(f"/api/v1/message/{mensaje_id}/part/{adjunto['PartID']}") == pdf
