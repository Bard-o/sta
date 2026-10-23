"""Pruebas de la cola de correos (issue #5: HU-08, RF-56, RNF-05, RNF-21)."""

import http.client
import itertools
import json
import logging
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app.core import mail as modulo_mail
from app.core import planificador as modulo_planificador
from app.core.config import Settings, get_settings
from app.core.db import CorreoEnCola
from app.core.mail import (
    ENVIADO,
    ESPERA_BASE,
    ESPERA_MAXIMA,
    FALLIDO,
    INTERVALO_ENVIO,
    MAX_INTENTOS,
    NOMBRE_TAREA,
    PENDIENTE,
    encolar_correo,
    enviar_correo,
    enviar_pendientes,
    espera_para,
)
from app.core.planificador import TICK, Planificador, cargar_tareas_de_modulos
from app.core.testing import SmtpFalso

DESTINO = "laura@correo.test"
CINCO_MINUTOS = timedelta(minutes=5)


class RelojControlado:
    def __init__(self, ahora: datetime) -> None:
        self.ahora = ahora

    def __call__(self) -> datetime:
        return self.ahora

    def avanzar(self, delta: timedelta) -> None:
        self.ahora += delta


@pytest.fixture(autouse=True)
def _logger_activo() -> None:
    # fileConfig de Alembic (al migrar la base de tests) desactiva los loggers ya creados.
    modulo_mail.logger.disabled = False


@pytest.fixture
def sesion_real(engine_de_tests: Engine) -> Iterator[Session]:
    """Sesión que confirma de verdad (para probar entre conexiones); limpia la cola al final."""
    sesion = Session(engine_de_tests, expire_on_commit=False)
    try:
        yield sesion
    finally:
        sesion.rollback()
        sesion.execute(delete(CorreoEnCola))
        sesion.commit()
        sesion.close()


def _despues() -> datetime:
    """Una hora posterior a la de cualquier correo recién encolado."""
    return datetime.now(UTC) + timedelta(minutes=1)


def _encolar(db: Session, destinatario: str = DESTINO, asunto: str = "Asunto") -> CorreoEnCola:
    """Encola y confirma un correo; devuelve su fila."""
    correo_id = encolar_correo(db, destinatario, asunto, "Texto")
    db.commit()
    return db.get_one(CorreoEnCola, correo_id)


def _filas(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def test_encolar_y_revertir_no_deja_nada_en_la_cola(db: Session, smtp_falso: SmtpFalso):
    """Criterio 1 del issue #5: si la transacción se revierte, el correo no sale."""
    encolar_correo(db, DESTINO, "Asunto", "Texto")
    assert db.scalar(select(func.count()).select_from(CorreoEnCola)) == 1
    db.rollback()
    assert _filas(db) == []
    assert enviar_pendientes(db, _despues()) == 0
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


def test_un_correo_confirmado_sale_en_la_siguiente_vuelta(db: Session, smtp_falso: SmtpFalso):
    """HU-08, criterio 4: el correo confirmado sale con sus encabezados y su versión HTML."""
    encolar_correo(db, DESTINO, "Bienvenida", "Hola Laura", "<p>Hola Laura</p>")
    db.commit()
    ahora = _despues()
    assert enviar_pendientes(db, ahora) == 1
    (mensaje,) = smtp_falso.enviados
    assert mensaje["To"] == DESTINO
    assert mensaje["Subject"] == "Bienvenida"
    assert mensaje["From"] == get_settings().mail_from
    assert mensaje.get_body(("html",)) is not None
    (fila,) = _filas(db)
    assert (fila.estado, fila.intentos, fila.enviado_en) == (ENVIADO, 1, ahora)


def test_un_correo_encolado_sale_antes_de_cinco_minutos(
    engine_de_tests: Engine, sesion_real: Session, smtp_falso: SmtpFalso
):
    """HU-08, RF-56, criterio 4: con el planificador real el correo sale en menos de 5 minutos."""
    inicio = _despues()
    reloj = RelojControlado(inicio)
    planificador = Planificador(engine=engine_de_tests, reloj=reloj)
    planificador.registrar(NOMBRE_TAREA, enviar_pendientes, cada=INTERVALO_ENVIO)
    planificador.ejecutar_vencidas()  # vuelta de arranque, con la cola vacía
    _encolar(sesion_real)
    encolado_en = reloj.ahora
    while not smtp_falso.enviados and reloj.ahora - encolado_en <= CINCO_MINUTOS:
        reloj.avanzar(TICK)
        planificador.ejecutar_vencidas()
    assert len(smtp_falso.enviados) == 1
    assert reloj.ahora - encolado_en <= CINCO_MINUTOS


def test_la_tarea_de_correos_queda_registrada_al_cargar_las_tareas():
    """HU-08: la tarea de core se registra sola y su espera máxima cabe en 5 minutos."""
    cargar_tareas_de_modulos()
    assert NOMBRE_TAREA in modulo_planificador.planificador.tareas
    assert INTERVALO_ENVIO + TICK <= CINCO_MINUTOS


def test_al_arrancar_sale_lo_que_quedo_pendiente_con_el_servidor_apagado(
    db: Session, smtp_falso: SmtpFalso
):
    """HU-18, RNF-21: lo encolado hace horas sale en la primera vuelta."""
    ahora = _despues()
    fila = _encolar(db)
    fila.proximo_intento_en = ahora - timedelta(hours=3)
    db.commit()
    assert enviar_pendientes(db, ahora) == 1
    assert len(smtp_falso.enviados) == 1


def test_un_correo_entregado_no_se_envia_dos_veces(db: Session, smtp_falso: SmtpFalso):
    """Criterio 2 del issue #5: un correo enviado nunca se reenvía."""
    ahora = _despues()
    fila = _encolar(db)
    assert enviar_pendientes(db, ahora) == 1
    assert enviar_pendientes(db, ahora + timedelta(hours=1)) == 0
    fila.proximo_intento_en = ahora - timedelta(days=1)
    db.commit()
    assert enviar_pendientes(db, ahora + timedelta(hours=2)) == 0
    assert len(smtp_falso.enviados) == 1


def test_otro_proceso_salta_el_correo_que_ya_esta_tomado(
    engine_de_tests: Engine, sesion_real: Session, smtp_falso: SmtpFalso
):
    """Criterio 2 del issue #5: SKIP LOCKED evita que dos procesos envíen el mismo correo."""
    fila = _encolar(sesion_real)
    ahora = _despues()
    with engine_de_tests.connect() as otra, otra.begin():
        otra.execute(text("SELECT id FROM cola_correos WHERE id = :id FOR UPDATE"), {"id": fila.id})
        assert enviar_pendientes(sesion_real, ahora) == 0
    assert smtp_falso.enviados == []
    assert enviar_pendientes(sesion_real, ahora) == 1


def test_si_smtp_falla_se_reintenta_y_luego_sale(db: Session, smtp_falso: SmtpFalso):
    """Criterio 3 del issue #5, RNF-21: si SMTP falla el correo espera y sale al volver."""
    t0 = _despues()
    fila = _encolar(db)
    smtp_falso.sin_conexion = True
    assert enviar_pendientes(db, t0) == 0
    db.refresh(fila)
    assert (fila.estado, fila.intentos) == (PENDIENTE, 1)
    assert fila.proximo_intento_en == t0 + ESPERA_BASE
    assert "ConnectionRefusedError" in (fila.ultimo_error or "")

    smtp_falso.sin_conexion = False
    assert enviar_pendientes(db, t0 + timedelta(seconds=30)) == 0
    assert smtp_falso.conexiones == []

    assert enviar_pendientes(db, t0 + ESPERA_BASE) == 1
    db.refresh(fila)
    assert (fila.estado, fila.intentos) == (ENVIADO, 2)


def test_la_espera_entre_reintentos_crece_hasta_cinco_minutos():
    """RNF-21: 1, 2 y 4 minutos y luego 5; nunca decrece ni pasa de 10 min tras volver SMTP."""
    assert [espera_para(n) for n in (1, 2, 3)] == [timedelta(minutes=m) for m in (1, 2, 4)]
    esperas = [espera_para(n) for n in range(1, 40)]
    assert esperas == sorted(esperas)
    assert max(esperas) == ESPERA_MAXIMA <= CINCO_MINUTOS
    peor_caso = ESPERA_MAXIMA + INTERVALO_ENVIO + TICK
    assert peor_caso <= timedelta(minutes=10)


def test_el_fallo_definitivo_queda_en_los_logs_y_no_se_reintenta(
    db: Session, smtp_falso: SmtpFalso, caplog: pytest.LogCaptureFixture
):
    """Criterio 3 del issue #5: tras MAX_INTENTOS el correo falla y queda en los logs."""
    fila = _encolar(db)
    smtp_falso.sin_conexion = True
    ahora = _despues()
    esperas = []
    with caplog.at_level(logging.WARNING, logger=modulo_mail.logger.name):
        for _ in range(MAX_INTENTOS):
            assert enviar_pendientes(db, ahora) == 0
            db.refresh(fila)
            if fila.estado == PENDIENTE:
                esperas.append(fila.proximo_intento_en - ahora)
                ahora = fila.proximo_intento_en
    assert esperas == [espera_para(n) for n in range(1, MAX_INTENTOS)]
    assert (fila.estado, fila.intentos) == (FALLIDO, MAX_INTENTOS)
    errores = [r for r in caplog.records if r.levelno == logging.ERROR]
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(errores) == 1
    assert str(fila.id) in errores[0].getMessage()
    assert len(avisos) == MAX_INTENTOS - 1

    smtp_falso.sin_conexion = False
    assert enviar_pendientes(db, ahora + timedelta(days=1)) == 0
    assert smtp_falso.enviados == []


def test_una_falla_del_servidor_corta_la_vuelta(db: Session, smtp_falso: SmtpFalso):
    """RNF-21: si el servidor SMTP no responde no se intenta el resto de la cola."""
    primero = _encolar(db, asunto="Primero")
    segundo = _encolar(db, asunto="Segundo")
    smtp_falso.sin_conexion = True
    assert enviar_pendientes(db, _despues()) == 0
    db.refresh(primero)
    db.refresh(segundo)
    assert (primero.intentos, segundo.intentos) == (1, 0)


def test_un_destinatario_rechazado_no_detiene_a_los_demas(db: Session, smtp_falso: SmtpFalso):
    """Criterio 3 del issue #5: el rechazo de un destinatario no frena los otros correos."""
    malo = _encolar(db, "malo@correo.test", "Malo")
    bueno = _encolar(db, DESTINO, "Bueno")
    smtp_falso.rechazados.add("malo@correo.test")
    assert enviar_pendientes(db, _despues()) == 1
    db.refresh(malo)
    db.refresh(bueno)
    assert bueno.estado == ENVIADO
    assert (malo.estado, malo.intentos) == (PENDIENTE, 1)
    assert "SMTPRecipientsRefused" in (malo.ultimo_error or "")


def test_la_vuelta_respeta_el_tope_de_correos(
    db: Session, smtp_falso: SmtpFalso, monkeypatch: pytest.MonkeyPatch
):
    """RNF-18: una vuelta procesa a lo más LOTE_POR_VUELTA correos; el resto sale después."""
    monkeypatch.setattr(modulo_mail, "LOTE_POR_VUELTA", 2)
    for numero in range(3):
        _encolar(db, asunto=f"Correo {numero}")
    ahora = _despues()
    assert enviar_pendientes(db, ahora) == 2
    assert enviar_pendientes(db, ahora) == 1


def test_la_vuelta_se_detiene_al_agotar_su_tiempo(
    db: Session, smtp_falso: SmtpFalso, monkeypatch: pytest.MonkeyPatch
):
    """RNF-18: una vuelta lenta se corta para no retrasar las demás tareas programadas."""
    monkeypatch.setattr(modulo_mail, "_monotonico", itertools.count(0, 15).__next__)
    for numero in range(3):
        _encolar(db, asunto=f"Correo {numero}")
    assert enviar_pendientes(db, _despues()) == 1


def test_una_vuelta_abre_una_sola_conexion_smtp(db: Session, smtp_falso: SmtpFalso):
    """RNF-18: los correos de una vuelta comparten una conexión SMTP."""
    for numero in range(3):
        _encolar(db, asunto=f"Correo {numero}")
    assert enviar_pendientes(db, _despues()) == 3
    assert len(smtp_falso.conexiones) == 1
    assert len(smtp_falso.enviados) == 3


def test_se_usa_el_smtp_de_la_configuracion_que_en_desarrollo_es_mailpit(
    db: Session, smtp_falso: SmtpFalso
):
    """Criterio 5 del issue #5: el servidor sale de la configuración; por defecto es Mailpit."""
    _encolar(db)
    assert enviar_pendientes(db, _despues()) == 1
    settings = get_settings()
    assert smtp_falso.conexiones == [(settings.smtp_host, settings.smtp_port)]
    assert Settings.model_fields["smtp_host"].default == "mailpit"
    assert Settings.model_fields["smtp_port"].default == 1025


def _asuntos_en_mailpit() -> list[str]:
    conexion = http.client.HTTPConnection(get_settings().smtp_host, 8025, timeout=5)
    try:
        conexion.request("GET", "/api/v1/messages?limit=100")
        cuerpo = json.loads(conexion.getresponse().read())
    finally:
        conexion.close()
    return [mensaje["Subject"] for mensaje in cuerpo["messages"]]


def test_en_desarrollo_el_correo_encolado_llega_a_mailpit(db: Session):
    """Criterio 5 del issue #5: el correo encolado llega de verdad a la bandeja de Mailpit."""
    asunto = f"Prueba de la cola {uuid.uuid4()}"
    encolar_correo(db, DESTINO, asunto, "Texto de prueba")
    db.commit()
    assert enviar_pendientes(db, _despues()) == 1
    limite = time.monotonic() + 10
    while time.monotonic() < limite:
        if asunto in _asuntos_en_mailpit():
            return
        time.sleep(0.5)
    pytest.fail("El correo no apareció en Mailpit (http://localhost:8025) en 10 segundos.")
