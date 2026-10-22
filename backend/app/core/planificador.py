"""Planificador de procesos programados (RNF-18, HU-18).

Los módulos registran sus tareas periódicas al final de su `service.py`:

    registrar_tarea("vuelos.marcar_realizados", marcar_realizados, cada=timedelta(minutes=1))

La función recibe `(db, ahora)`: una sesión de SQLAlchemy y la hora actual en UTC. No hace commit:
el planificador confirma si la función termina bien y deshace si falla.

- Al arrancar el servidor corre una vez cada tarea, para procesar lo que venció con el servidor
  apagado (HU-18).
- Un hilo revisa cada `TICK` qué tareas les toca. Con `cada` de 1 minuto una tarea corre como
  máximo 2 minutos después de su hora (RNF-18).
- Con varios procesos del backend, un lock de asesoría de PostgreSQL evita que una tarea corra dos
  veces al mismo tiempo.
- Un error en una tarea se escribe en los logs y no detiene al planificador ni a las demás tareas.
- Si el servidor estuvo ocupado y una tarea se atrasó, corre una sola vez (no en ráfaga).
"""

import hashlib
import importlib
import logging
import pkgutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import engine as _engine_app

logger = logging.getLogger(__name__)

FuncionTarea = Callable[[Session, datetime], object]
Reloj = Callable[[], datetime]
Resultado = Literal["ejecutada", "fallida", "omitida"]

INTERVALO_POR_DEFECTO = timedelta(minutes=1)
TICK = timedelta(seconds=10)
RETRASO_MAXIMO = timedelta(minutes=2)  # RNF-18
_PREFIJO_LOCK = "sta.planificador:"


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def clave_de_lock(nombre: str) -> int:
    """Clave bigint estable (igual en todos los procesos) para el lock de la tarea."""
    resumen = hashlib.blake2b((_PREFIJO_LOCK + nombre).encode(), digest_size=8).digest()
    return int.from_bytes(resumen, "big", signed=True)


@dataclass(slots=True)
class Tarea:
    nombre: str
    funcion: FuncionTarea
    cada: timedelta
    clave: int
    proxima: datetime | None = None


class Planificador:
    def __init__(
        self,
        *,
        engine: Engine = _engine_app,
        reloj: Reloj = ahora_utc,
        tick: timedelta = TICK,
    ) -> None:
        self._engine = engine
        self._reloj = reloj
        self._tick = tick
        self._sesiones = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self._tareas: dict[str, Tarea] = {}
        self._hilo: threading.Thread | None = None
        self._detener: threading.Event | None = None

    def registrar(
        self,
        nombre: str,
        funcion: FuncionTarea,
        *,
        cada: timedelta = INTERVALO_POR_DEFECTO,
    ) -> None:
        if not nombre.strip():
            raise ValueError("La tarea necesita un nombre.")
        if nombre in self._tareas:
            raise ValueError(f"Ya hay una tarea registrada con el nombre {nombre}.")
        if cada <= timedelta(0):
            raise ValueError("El intervalo de la tarea debe ser mayor que cero.")
        self._tareas[nombre] = Tarea(nombre, funcion, cada, clave_de_lock(nombre))

    @property
    def tareas(self) -> tuple[str, ...]:
        return tuple(self._tareas)

    @property
    def tick(self) -> timedelta:
        return self._tick

    @property
    def en_marcha(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def proxima_ejecucion(self, nombre: str) -> datetime | None:
        return self._tareas[nombre].proxima

    def ejecutar_vencidas(self) -> dict[str, Resultado]:
        """Ejecuta las tareas que ya les toca y devuelve el resultado de cada una."""
        resultados: dict[str, Resultado] = {}
        for tarea in list(self._tareas.values()):
            ahora = self._reloj()
            if tarea.proxima is not None and ahora < tarea.proxima:
                continue
            tarea.proxima = ahora + tarea.cada
            resultados[tarea.nombre] = self._ejecutar(tarea, ahora)
        return resultados

    def _ejecutar(self, tarea: Tarea, ahora: datetime) -> Resultado:
        try:
            with self._engine.connect() as conn_lock, conn_lock.begin():
                tomado = conn_lock.scalar(
                    text("SELECT pg_try_advisory_xact_lock(CAST(:clave AS bigint))"),
                    {"clave": tarea.clave},
                )
                if not tomado:
                    logger.info(
                        "La tarea programada %s ya corre en otro proceso; se omite.", tarea.nombre
                    )
                    return "omitida"
                with self._sesiones() as db:
                    tarea.funcion(db, ahora)
                    # Se confirma antes de soltar el lock (termina con la transacción del lock).
                    db.commit()
            return "ejecutada"
        except Exception:
            logger.exception(
                "La tarea programada %s falló; se reintenta en la siguiente vuelta.", tarea.nombre
            )
            return "fallida"

    def _bucle(self, detener: threading.Event) -> None:
        # La primera vuelta es inmediata: procesa lo que venció con el servidor apagado (HU-18).
        while True:
            try:
                self.ejecutar_vencidas()
            except Exception:
                logger.exception("El planificador tuvo un error inesperado; sigue en marcha.")
            if detener.wait(self._tick.total_seconds()):
                return

    def iniciar(self) -> None:
        if self.en_marcha:
            return
        evento = threading.Event()
        self._detener = evento
        self._hilo = threading.Thread(
            target=self._bucle, args=(evento,), name="planificador", daemon=True
        )
        self._hilo.start()

    def detener(self, timeout: float = 10.0) -> None:
        if self._hilo is None or self._detener is None:
            return
        self._detener.set()
        self._hilo.join(timeout)
        if self._hilo.is_alive():
            logger.warning("El planificador no terminó en %s s.", timeout)


# Instancia del proceso: la que registran los módulos y arranca la app.
planificador = Planificador()


def registrar_tarea(
    nombre: str,
    funcion: FuncionTarea,
    *,
    cada: timedelta = INTERVALO_POR_DEFECTO,
) -> None:
    """Registra una tarea periódica. Es la función pública para los módulos."""
    planificador.registrar(nombre, funcion, cada=cada)


def cargar_tareas_de_modulos() -> None:
    """Importa el `service.py` de cada módulo para que registren sus tareas."""
    from app import modules

    for modulo in pkgutil.iter_modules(modules.__path__):
        if not modulo.ispkg:
            continue
        nombre = f"app.modules.{modulo.name}.service"
        try:
            importlib.import_module(nombre)
        except ModuleNotFoundError as exc:
            if exc.name != nombre:
                raise
