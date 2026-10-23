"""Pruebas de la cola de correos (issue #5: HU-08, RF-56, RNF-05, RNF-21)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import CorreoEnCola
from app.core.mail import PENDIENTE, encolar_correo, enviar_correo
from app.core.testing import SmtpFalso

DESTINO = "laura@correo.test"


def _filas(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def test_encolar_y_revertir_no_deja_nada_en_la_cola(db: Session, smtp_falso: SmtpFalso):
    """Criterio 1 del issue #5: si la transacción se revierte, el correo no sale."""
    encolar_correo(db, DESTINO, "Asunto", "Texto")
    assert db.scalar(select(func.count()).select_from(CorreoEnCola)) == 1
    db.rollback()
    assert _filas(db) == []
    assert smtp_falso.enviados == []


def test_encolar_guarda_el_correo_pendiente_sin_enviarlo(db: Session, smtp_falso: SmtpFalso):
    """Criterio 1 del issue #5: encolar guarda el correo en la transacción y no hace commit."""
    correo_id = encolar_correo(db, DESTINO, "Asunto", "Texto", "<p>Texto</p>")
    (fila,) = _filas(db)
    assert fila.id == correo_id
    assert (fila.estado, fila.intentos, fila.html) == (PENDIENTE, 0, "<p>Texto</p>")
    assert smtp_falso.enviados == []


def test_encolar_rechaza_encabezados_con_saltos_de_linea(db: Session):
    """Criterio 1 del issue #5: un asunto con saltos de línea es un error de programación."""
    with pytest.raises(ValueError):
        encolar_correo(db, DESTINO, "a\nBcc: x@y", "Texto")
    assert _filas(db) == []


def test_enviar_correo_sincrono_sigue_funcionando(smtp_falso: SmtpFalso):
    """RNF-05: el envío inmediato que ya usan los módulos no cambió."""
    enviar_correo(DESTINO, "Asunto", "Texto")
    assert len(smtp_falso.enviados) == 1
    assert len(smtp_falso.conexiones) == 1
