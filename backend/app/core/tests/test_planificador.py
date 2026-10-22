"""Pruebas del planificador de procesos programados (issue #4: RNF-18, HU-18)."""

import logging
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core import planificador as modulo_planificador
from app.core.config import get_settings
from app.core.planificador import (
    RETRASO_MAXIMO,
    TICK,
    Planificador,
    cargar_tareas_de_modulos,
    clave_de_lock,
    registrar_tarea,
)
from app.main import app

INICIO = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
UN_MINUTO = timedelta(minutes=1)


class RelojControlado:
    def __init__(self, ahora: datetime) -> None:
        self.ahora = ahora

    def __call__(self) -> datetime:
        return self.ahora

    def avanzar(self, delta: timedelta) -> None:
        self.ahora += delta


class Llamadas:
    """Tarea falsa: solo anota con qué hora la llamaron."""

    def __init__(self) -> None:
        self.horas: list[datetime] = []

    def __call__(self, db: Session, ahora: datetime) -> None:
        self.horas.append(ahora)


@pytest.fixture(autouse=True)
def _logger_activo() -> None:
    # fileConfig de Alembic (al migrar la base de tests) desactiva los loggers ya creados.
    modulo_planificador.logger.disabled = False


@pytest.fixture
def reloj() -> RelojControlado:
    return RelojControlado(INICIO)


@pytest.fixture
def planificador_prueba(engine_de_tests: Engine, reloj: RelojControlado) -> Planificador:
    return Planificador(engine=engine_de_tests, reloj=reloj)


def test_registrar_tarea_agrega_al_planificador_del_proceso(monkeypatch: pytest.MonkeyPatch):
    """Criterio 1 del issue #4: un módulo registra una tarea con una función pública de core."""
    nuevo = Planificador()
    monkeypatch.setattr(modulo_planificador, "planificador", nuevo)
    registrar_tarea("prueba.accion", Llamadas(), cada=timedelta(minutes=5))
    assert nuevo.tareas == ("prueba.accion",)


def test_registrar_rechaza_nombre_repetido_vacio_o_intervalo_no_positivo(
    planificador_prueba: Planificador,
):
    """Criterio 1 del issue #4: el registro valida nombre único e intervalo positivo."""
    planificador_prueba.registrar("a.b", Llamadas())
    with pytest.raises(ValueError):
        planificador_prueba.registrar("a.b", Llamadas())
    with pytest.raises(ValueError):
        planificador_prueba.registrar("   ", Llamadas())
    with pytest.raises(ValueError):
        planificador_prueba.registrar("c.d", Llamadas(), cada=timedelta(0))
    with pytest.raises(ValueError):
        planificador_prueba.registrar("c.d", Llamadas(), cada=timedelta(seconds=-5))
    assert planificador_prueba.tareas == ("a.b",)


def test_la_tarea_corre_cuando_le_toca(planificador_prueba: Planificador, reloj: RelojControlado):
    """Criterio 1 del issue #4: con el reloj controlado la tarea corre en su intervalo."""
    sesiones: list[int | None] = []

    def tarea(db: Session, ahora: datetime) -> None:
        sesiones.append(db.scalar(text("SELECT 1")))

    planificador_prueba.registrar("prueba.tarea", tarea, cada=UN_MINUTO)
    assert planificador_prueba.ejecutar_vencidas() == {"prueba.tarea": "ejecutada"}
    reloj.avanzar(timedelta(seconds=30))
    assert planificador_prueba.ejecutar_vencidas() == {}
    reloj.avanzar(timedelta(seconds=30))
    assert planificador_prueba.ejecutar_vencidas() == {"prueba.tarea": "ejecutada"}
    assert sesiones == [1, 1]
    assert planificador_prueba.proxima_ejecucion("prueba.tarea") == INICIO + 2 * UN_MINUTO


def test_ninguna_ejecucion_se_atrasa_mas_de_dos_minutos(
    planificador_prueba: Planificador, reloj: RelojControlado
):
    """RNF-18: con cada=1 min y vueltas cada TICK, el atraso nunca pasa de 2 minutos."""
    tarea = Llamadas()
    planificador_prueba.registrar("prueba.tarea", tarea, cada=UN_MINUTO)
    fin = INICIO + timedelta(minutes=10)
    while reloj.ahora <= fin:
        planificador_prueba.ejecutar_vencidas()
        reloj.avanzar(TICK)
    esperadas = [INICIO + n * UN_MINUTO for n in range(11)]
    assert len(tarea.horas) == len(esperadas)
    for esperada, real in zip(esperadas, tarea.horas, strict=True):
        assert timedelta(0) <= real - esperada <= RETRASO_MAXIMO


def test_una_tarea_atrasada_corre_una_vez_sin_rafaga(
    planificador_prueba: Planificador, reloj: RelojControlado
):
    """RNF-18: tras un atraso largo la tarea corre una vez, no una vez por intervalo perdido."""
    tarea = Llamadas()
    planificador_prueba.registrar("prueba.tarea", tarea, cada=UN_MINUTO)
    planificador_prueba.ejecutar_vencidas()
    reloj.avanzar(timedelta(minutes=30))
    assert planificador_prueba.ejecutar_vencidas() == {"prueba.tarea": "ejecutada"}
    assert planificador_prueba.ejecutar_vencidas() == {}
    assert len(tarea.horas) == 2


def test_al_arrancar_se_ejecutan_todas_las_tareas_una_vez(planificador_prueba: Planificador):
    """HU-18: al arrancar corre cada tarea una vez, sea cual sea su intervalo."""
    llamadas = {"a.minuto": Llamadas(), "b.hora": Llamadas(), "c.dia": Llamadas()}
    planificador_prueba.registrar("a.minuto", llamadas["a.minuto"], cada=UN_MINUTO)
    planificador_prueba.registrar("b.hora", llamadas["b.hora"], cada=timedelta(hours=1))
    planificador_prueba.registrar("c.dia", llamadas["c.dia"], cada=timedelta(days=1))
    assert planificador_prueba.ejecutar_vencidas() == {
        "a.minuto": "ejecutada",
        "b.hora": "ejecutada",
        "c.dia": "ejecutada",
    }
    assert planificador_prueba.ejecutar_vencidas() == {}
    assert all(len(tarea.horas) == 1 for tarea in llamadas.values())


def test_el_hilo_ejecuta_al_iniciar_y_se_detiene(engine_de_tests: Engine):
    """HU-18: el hilo ejecuta las tareas apenas inicia y se detiene limpiamente."""
    corrio = threading.Event()

    def tarea(db: Session, ahora: datetime) -> None:
        corrio.set()

    real = Planificador(engine=engine_de_tests, tick=timedelta(milliseconds=20))
    real.registrar("prueba.tarea", tarea, cada=UN_MINUTO)
    real.iniciar()
    try:
        assert real.en_marcha
        assert corrio.wait(5)
        real.iniciar()  # una segunda llamada no crea otro hilo
    finally:
        real.detener()
    assert not real.en_marcha


def test_el_ciclo_de_vida_de_la_app_inicia_y_detiene_el_planificador(
    monkeypatch: pytest.MonkeyPatch,
):
    """HU-18: la app inicia el planificador al arrancar y lo detiene al apagarse."""
    eventos: list[str] = []
    monkeypatch.setattr(get_settings(), "planificador_activo", True)
    monkeypatch.setattr("app.main.cargar_tareas_de_modulos", lambda: eventos.append("cargar"))
    monkeypatch.setattr(
        "app.main.planificador.iniciar", lambda: eventos.append("iniciar"), raising=True
    )
    monkeypatch.setattr(
        "app.main.planificador.detener", lambda: eventos.append("detener"), raising=True
    )
    with TestClient(app):
        assert eventos == ["cargar", "iniciar"]
    assert eventos == ["cargar", "iniciar", "detener"]


def test_los_tests_no_arrancan_el_planificador_real(client: TestClient):
    """Criterio 2 del issue #4: la suite no deja correr el hilo real."""
    assert not modulo_planificador.planificador.en_marcha


def test_con_el_lock_tomado_por_otra_conexion_la_tarea_se_omite(
    engine_de_tests: Engine, planificador_prueba: Planificador, reloj: RelojControlado
):
    """Criterio 3 del issue #4: si otro proceso tiene el lock, la tarea no corre."""
    tarea = Llamadas()
    planificador_prueba.registrar("prueba.tarea", tarea, cada=UN_MINUTO)
    clave = clave_de_lock("prueba.tarea")
    with engine_de_tests.connect() as otra, otra.begin():
        assert otra.scalar(text("SELECT pg_try_advisory_xact_lock(:c)"), {"c": clave})
        assert planificador_prueba.ejecutar_vencidas() == {"prueba.tarea": "omitida"}
    assert tarea.horas == []
    reloj.avanzar(UN_MINUTO)
    assert planificador_prueba.ejecutar_vencidas() == {"prueba.tarea": "ejecutada"}
    assert len(tarea.horas) == 1


def test_dos_instancias_no_ejecutan_la_misma_tarea_a_la_vez(engine_de_tests: Engine):
    """Criterio 3 del issue #4: dos procesos no corren la misma tarea al mismo tiempo."""
    entro = threading.Event()
    soltar = threading.Event()
    corridas: list[str] = []

    def lenta(db: Session, ahora: datetime) -> None:
        corridas.append("lenta")
        entro.set()
        assert soltar.wait(5)

    def rapida(db: Session, ahora: datetime) -> None:
        corridas.append("rapida")

    primero = Planificador(engine=engine_de_tests, reloj=lambda: INICIO)
    segundo = Planificador(engine=engine_de_tests, reloj=lambda: INICIO)
    primero.registrar("prueba.tarea", lenta, cada=UN_MINUTO)
    segundo.registrar("prueba.tarea", rapida, cada=UN_MINUTO)

    resultado: dict[str, object] = {}
    hilo = threading.Thread(target=lambda: resultado.update(primero.ejecutar_vencidas()))
    hilo.start()
    try:
        assert entro.wait(5)
        assert segundo.ejecutar_vencidas() == {"prueba.tarea": "omitida"}
    finally:
        soltar.set()
        hilo.join(5)
    assert resultado == {"prueba.tarea": "ejecutada"}
    assert corridas == ["lenta"]


def test_el_lock_se_libera_aunque_la_tarea_falle(
    engine_de_tests: Engine, planificador_prueba: Planificador, reloj: RelojControlado
):
    """Criterio 3 del issue #4: un fallo no deja el lock tomado."""

    def falla(db: Session, ahora: datetime) -> None:
        raise RuntimeError("falla de prueba")

    planificador_prueba.registrar("prueba.tarea", falla, cada=UN_MINUTO)
    assert planificador_prueba.ejecutar_vencidas() == {"prueba.tarea": "fallida"}
    with engine_de_tests.connect() as otra, otra.begin():
        libre = otra.scalar(
            text("SELECT pg_try_advisory_xact_lock(:c)"), {"c": clave_de_lock("prueba.tarea")}
        )
    assert libre


def test_una_tarea_que_falla_queda_en_los_logs_y_no_detiene_a_las_demas(
    planificador_prueba: Planificador,
    reloj: RelojControlado,
    caplog: pytest.LogCaptureFixture,
):
    """Criterio 4 del issue #4: el error se registra y las otras tareas siguen."""
    intentos = {"n": 0}

    def inestable(db: Session, ahora: datetime) -> None:
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("falla de prueba")

    sana = Llamadas()
    planificador_prueba.registrar("prueba.inestable", inestable, cada=UN_MINUTO)
    planificador_prueba.registrar("prueba.sana", sana, cada=UN_MINUTO)
    with caplog.at_level(logging.ERROR, logger=modulo_planificador.logger.name):
        resultado = planificador_prueba.ejecutar_vencidas()
    assert resultado == {"prueba.inestable": "fallida", "prueba.sana": "ejecutada"}
    registros = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(registros) == 1
    assert "prueba.inestable" in registros[0].getMessage()
    assert registros[0].exc_info is not None
    assert len(sana.horas) == 1

    reloj.avanzar(UN_MINUTO)
    assert planificador_prueba.ejecutar_vencidas() == {
        "prueba.inestable": "ejecutada",
        "prueba.sana": "ejecutada",
    }


def test_el_planificador_sigue_si_la_base_de_datos_no_responde(reloj: RelojControlado):
    """Criterio 4 del issue #4: sin base de datos la tarea falla pero no explota el planificador."""
    inalcanzable = create_engine(
        "postgresql+psycopg://sta:sta@127.0.0.1:1/nada", connect_args={"connect_timeout": 2}
    )
    try:
        sin_bd = Planificador(engine=inalcanzable, reloj=reloj)
        sin_bd.registrar("prueba.tarea", Llamadas(), cada=UN_MINUTO)
        assert sin_bd.ejecutar_vencidas() == {"prueba.tarea": "fallida"}
    finally:
        inalcanzable.dispose()


def test_clave_de_lock_es_estable_distinta_por_nombre_y_cabe_en_bigint():
    """Criterio 3 del issue #4: la clave del lock es la misma en todos los procesos."""
    assert clave_de_lock("vuelos.marcar_realizados") == clave_de_lock("vuelos.marcar_realizados")
    assert clave_de_lock("vuelos.marcar_realizados") != clave_de_lock("vuelos.vencer_promociones")
    for nombre in ("a", "vuelos.marcar_realizados", "x" * 200):
        assert -(2**63) <= clave_de_lock(nombre) < 2**63


def test_cargar_tareas_de_modulos_importa_los_service():
    """Criterio 1 del issue #4: los módulos registran sus tareas al importar su service."""
    sys.modules.pop("app.modules.vuelos.service", None)
    cargar_tareas_de_modulos()
    assert "app.modules.vuelos.service" in sys.modules


@pytest.fixture(autouse=True)
def _sin_hilos_colgados() -> Iterator[None]:
    yield
    assert not any(h.name == "planificador" and h.is_alive() for h in threading.enumerate())
