"""Correo de cada noticia nueva a los clientes suscritos (HU-08, RF-56).

Cada test cita el criterio de aceptación que cubre. El envío real lo hace la tarea
`core.enviar_correos` cada minuto; aquí se prueba el encolado en la transacción de publicación,
los enlaces, la baja sin sesión y el rollback.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import mail
from app.core.config import get_settings
from app.core.db import CorreoEnCola
from app.core.security import Rol
from app.core.testing import SmtpFalso
from app.modules.noticias import service
from app.modules.noticias.models import Noticia
from app.modules.noticias.tests.fabricas import promocion_publicada, vuelo_publicado
from app.modules.usuarios import service as usuarios_service
from app.modules.usuarios.service import SuscriptorNoticias

BAJA = "/api/v1/usuarios/suscripcion/baja"


def _correos(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def _simular_suscriptores(
    monkeypatch: pytest.MonkeyPatch, *suscriptores: SuscriptorNoticias
) -> None:
    """Reemplaza `usuarios.suscriptores_noticias` por la lista dada (RF-56)."""
    monkeypatch.setattr(usuarios_service, "suscriptores_noticias", lambda _db: list(suscriptores))


def _cliente_suscrito(
    db: Session,
    crear_usuario: Callable[..., Any],
    *,
    nombre_usuario: str = "suscrito",
    email: str = "suscrito@example.com",
) -> Any:
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario=nombre_usuario, email=email)
    usuario.email_verificado = True
    db.commit()
    usuarios_service.cambiar_suscripcion(db, usuario.id, noticias=True)
    return usuario


def test_publicar_noticia_encola_un_correo_por_suscriptor_con_sus_dos_enlaces(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-08 CA-4 / RF-56: cada suscriptor recibe un correo con el vuelo y su baja."""
    suscriptores = [
        SuscriptorNoticias(
            usuario_id=1, email="ana@example.com", nombres="Ana", token_baja="token-ana"
        ),
        SuscriptorNoticias(
            usuario_id=2, email="luis@example.com", nombres="Luis", token_baja="token-luis"
        ),
    ]
    _simular_suscriptores(monkeypatch, *suscriptores)

    service.publicar_noticia_vuelo(db, vuelo_publicado())

    correos = _correos(db)
    assert [correo.destinatario for correo in correos] == [
        "ana@example.com",
        "luis@example.com",
    ]
    base = get_settings().frontend_url.rstrip("/")
    for correo, suscriptor in zip(correos, suscriptores, strict=True):
        assert correo.asunto == "Nuevo vuelo Pereira → Miami"
        assert correo.estado == "pendiente"
        for cuerpo in (correo.texto, correo.html or ""):
            assert f"{base}/vuelos/76" in cuerpo
            assert f"{base}/noticias/baja?token={suscriptor.token_baja}" in cuerpo
    # IU-05: la salida se muestra en la hora local de Pereira (UTC-5).
    assert "15/11/2026" in correos[0].texto
    assert "09:30" in correos[0].texto


def test_publicar_promocion_tambien_encola_su_correo(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-08 CA-4 / RF-56: la promoción también lleva el enlace al vuelo."""
    _simular_suscriptores(
        monkeypatch,
        SuscriptorNoticias(
            usuario_id=1, email="ana@example.com", nombres="Ana", token_baja="token-ana"
        ),
    )

    service.publicar_noticia_promocion(db, promocion_publicada())

    (correo,) = _correos(db)
    base = get_settings().frontend_url.rstrip("/")
    assert correo.asunto == "Promoción del 30 % en Pereira → Miami, económica"
    assert f"{base}/vuelos/76" in correo.texto
    assert f"{base}/noticias/baja?token=token-ana" in correo.texto


def test_solo_los_clientes_suscritos_reciben_el_correo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-08 CA-2 / RF-56: un cliente no suscrito no recibe el correo."""
    suscrito = _cliente_suscrito(db, crear_usuario)
    no_suscrito = crear_usuario(
        Rol.CLIENTE, nombre_usuario="no_suscrito", email="no-suscrito@example.com"
    )
    no_suscrito.email_verificado = True
    db.commit()

    service.publicar_noticia_vuelo(db, vuelo_publicado())

    (correo,) = _correos(db)
    assert correo.destinatario == suscrito.email


def test_el_enlace_de_baja_del_correo_da_de_baja_sin_sesion(
    client: TestClient, db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-08 CA-3: el enlace del correo da de baja sin iniciar sesión."""
    usuario = _cliente_suscrito(db, crear_usuario, nombre_usuario="baja", email="baja@example.com")
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    (correo,) = _correos(db)
    enlace = re.search(r"/noticias/baja\?token=(\S+)", correo.texto)
    assert enlace is not None

    respuesta = client.post(BAJA, json={"token": enlace.group(1)})

    assert respuesta.status_code == 204, respuesta.text
    db.refresh(usuario)
    assert usuario.suscrito_noticias is False


def test_el_correo_encolado_sale_en_la_siguiente_vuelta_de_la_cola(
    db: Session, monkeypatch: pytest.MonkeyPatch, smtp_falso: SmtpFalso
) -> None:
    """HU-08 CA-1 / RNF-05: la cola envía en menos de 5 min (la tarea corre cada minuto)."""
    _simular_suscriptores(
        monkeypatch,
        SuscriptorNoticias(
            usuario_id=1, email="ana@example.com", nombres="Ana", token_baja="token-ana"
        ),
    )
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    assert smtp_falso.enviados == []

    enviados = mail.enviar_pendientes(db, datetime.now(UTC) + timedelta(minutes=1))

    assert enviados == 1
    (mensaje,) = smtp_falso.enviados
    assert str(mensaje["To"]) == "ana@example.com"
    assert str(mensaje["Subject"]) == "Nuevo vuelo Pereira → Miami"


def test_el_rollback_de_la_publicacion_no_deja_correos(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-08 CA-5 / RNF-17: si la transacción se revierte, no sale ningún correo."""
    _simular_suscriptores(
        monkeypatch,
        SuscriptorNoticias(
            usuario_id=1, email="ana@example.com", nombres="Ana", token_baja="token-ana"
        ),
    )
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    assert len(_correos(db)) == 1

    db.rollback()

    assert _correos(db) == []
    assert list(db.scalars(select(Noticia))) == []
