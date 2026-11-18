"""Fixtures de pytest compartidas por todos los módulos (se cargan desde conftest.py).

- `db`: sesión sobre la base de datos de tests; todo lo que haga el test se deshace al final.
- `client`: TestClient de la API que usa esa misma sesión.
- `crear_usuario`: crea un usuario con rol y contraseña dados (`registro_completo=False` para un
  administrador con el registro incompleto, HU-12).
- `client_como`: TestClient con la sesión iniciada para un rol.
- `base_confirmada`: sesiones que confirman de verdad (una por hilo) para pruebas de concurrencia;
  borra lo confirmado y falla si quedan datos (#129).
- `smtp_falso`: reemplaza el servidor SMTP de app.core.mail (correos enviados, fallos simulados).
- `_sin_planificador_real` (automática): apaga el hilo del planificador en todos los tests.
- `archivos_dir` (autouse): los archivos de app.core.archivos van a un tmp_path del test,
  nunca al volumen real.
"""

import importlib
import pkgutil
import smtplib
import threading
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Self

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app import modules
from app.core.config import get_settings
from app.core.db import Base, get_db
from app.core.security import Rol
from app.main import app

CONTRASENA_TEST = "Clave1234"
CONEXIONES_SIMULTANEAS = 60  # 50 hilos (RNF-17) + holgura; PostgreSQL 16 admite 100
_ESPERA_LARGADA = 30  # s que un hilo espera a los demás en la barrera
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _url_de_tests() -> str:
    settings = get_settings()
    if settings.test_database_url:
        return settings.test_database_url
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _crear_base_si_no_existe(url: str) -> None:
    destino = make_url(url)
    admin = create_engine(destino.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        existe = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :nombre"),
            {"nombre": destino.database},
        )
        if not existe:
            conn.execute(text(f'CREATE DATABASE "{destino.database}"'))
    admin.dispose()


@pytest.fixture(autouse=True, scope="session")
def _sin_planificador_real() -> Iterator[None]:
    """El hilo del planificador nunca arranca en los tests (se prueba la clase con un reloj)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(get_settings(), "planificador_activo", False)
        yield


@pytest.fixture(scope="session")
def engine_de_tests() -> Iterator[Engine]:
    """Base de tests desde cero en cada corrida, migrada con Alembic (prueba las migraciones)."""
    url = _url_de_tests()
    _crear_base_si_no_existe(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = Config(str(_ALEMBIC_INI))
    config.attributes["url"] = url
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def archivos_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Los archivos subidos van a un directorio temporal del test, nunca al volumen real."""
    ruta = tmp_path / "archivos"  # no se crea: guardar() crea la raíz cuando hace falta
    monkeypatch.setattr(get_settings(), "archivos_dir", ruta)
    return ruta


class _ConexionSmtpFalsa:
    def __init__(self, enviados: list[EmailMessage], rechazados: set[str]) -> None:
        self._enviados = enviados
        self._rechazados = rechazados

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def send_message(self, mensaje: EmailMessage) -> None:
        destinatario = str(mensaje["To"])
        if destinatario in self._rechazados:
            raise smtplib.SMTPRecipientsRefused({destinatario: (550, b"Buzon inexistente")})
        self._enviados.append(mensaje)

    def quit(self) -> None:
        return None

    def close(self) -> None:
        return None


class SmtpFalso:
    """Servidor SMTP simulado que reemplaza smtplib.SMTP (fixture `smtp_falso`).

    enviados: mensajes aceptados; conexiones: (host, puerto) de cada conexión;
    sin_conexion=True: conectar lanza ConnectionRefusedError; rechazados: destinatarios que el
    servidor rechaza con SMTPRecipientsRefused.
    """

    def __init__(self) -> None:
        self.enviados: list[EmailMessage] = []
        self.conexiones: list[tuple[str, int]] = []
        self.sin_conexion = False
        self.rechazados: set[str] = set()

    def __call__(self, host: str, port: int, timeout: float | None = None) -> _ConexionSmtpFalsa:
        if self.sin_conexion:
            raise ConnectionRefusedError("SMTP simulado fuera de servicio")
        self.conexiones.append((host, port))
        return _ConexionSmtpFalsa(self.enviados, self.rechazados)


@pytest.fixture
def smtp_falso(monkeypatch: pytest.MonkeyPatch) -> SmtpFalso:
    """app.core.mail entrega a un servidor SMTP simulado (issue #5)."""
    servidor = SmtpFalso()
    monkeypatch.setattr(smtplib, "SMTP", servidor)
    return servidor


@pytest.fixture
def db(engine_de_tests: Engine) -> Iterator[Session]:
    """Sesión dentro de una transacción que se revierte al terminar el test.

    Los commit() del código bajo prueba se convierten en SAVEPOINT, así que no tocan la base.
    """
    with engine_de_tests.connect() as conn:
        transaccion = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaccion.rollback()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    # https para que la cookie de sesión viaje también con COOKIE_SECURE=true.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def crear_usuario(db: Session) -> Callable[..., Any]:
    from app.modules.usuarios import service as usuarios_service

    def _crear(
        rol: Rol = Rol.CLIENTE,
        *,
        nombre_usuario: str | None = None,
        contrasena: str = CONTRASENA_TEST,
        email: str | None = None,
        activo: bool = True,
        registro_completo: bool = True,
    ) -> Any:
        nombre = nombre_usuario or f"{rol.value}_test"
        usuario = usuarios_service.crear_usuario(
            db,
            nombre_usuario=nombre,
            contrasena=contrasena,
            rol=rol,
            email=email,
            activo=activo,
        )
        if not registro_completo:
            usuario.registro_completo = False
            db.commit()
        return usuario

    return _crear


@pytest.fixture
def client_como(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> Callable[[Rol], TestClient]:
    """`client_como(Rol.ADMIN)` crea un usuario de ese rol e inicia sesión con él."""

    def _como(rol: Rol) -> TestClient:
        usuario = crear_usuario(rol)
        respuesta = client.post(
            "/api/v1/auth/login",
            json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
        )
        if respuesta.status_code != 200:
            raise AssertionError(respuesta.text)
        return client

    return _como


def _tablas_de_hijas_a_padres() -> list[Table]:
    """Todas las tablas del proyecto, de las que dependen de otras a las que no dependen."""
    # Mismo descubrimiento que alembic/env.py: cada app/modules/<modulo>/models.py registra las
    # suyas en Base.metadata (las de core/db.py ya están registradas por el import de arriba).
    for modulo in pkgutil.iter_modules(modules.__path__):
        if modulo.ispkg:
            try:
                importlib.import_module(f"app.modules.{modulo.name}.models")
            except ModuleNotFoundError as exc:
                if exc.name != f"app.modules.{modulo.name}.models":
                    raise
    return list(reversed(Base.metadata.sorted_tables))


class BaseConfirmada:
    """Sesiones que confirman de verdad, una por hilo, sobre la base de tests (fixture
    `base_confirmada`, #129).

    `en_paralelo` lanza varios trabajos a la vez, cada uno con su propia sesión y su propia
    conexión. Lo que un trabajo confirma lo ven los demás. Al terminar el test, `limpiar` borra
    todo lo que se confirmó: las filas con id mayor que el que había al empezar.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        # Igual que SessionLocal de app/core/db.py.
        self._sesiones = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self._tablas = _tablas_de_hijas_a_padres()
        self._filas_iniciales = self._contar()
        self._ultimo_id = self._ultimos_ids()

    def sesion(self) -> Session:
        """Sesión nueva sobre su propia conexión; quien la pide la cierra."""
        return self._sesiones()

    def en_paralelo[T](self, trabajos: Sequence[Callable[[Session], T]]) -> list[T]:
        """Corre cada trabajo en su hilo y su sesión; todos arrancan a la vez.

        Cada hilo toma su conexión y espera en una barrera: nadie empieza hasta que todos
        tienen la suya, así que las transacciones se solapan de verdad. Devuelve los resultados
        en el orden de `trabajos`. Si alguno lanza una excepción, la relanza (la primera que no
        sea de la barrera) con una nota que dice cuántos hilos fallaron y por qué.
        """
        total = len(trabajos)
        if not 0 < total <= CONEXIONES_SIMULTANEAS:
            raise ValueError(f"Se admiten de 1 a {CONEXIONES_SIMULTANEAS} trabajos, no {total}.")
        barrera = threading.Barrier(total, timeout=_ESPERA_LARGADA)

        def _hilo(trabajo: Callable[[Session], T]) -> T:
            with self._sesiones() as sesion:
                try:
                    sesion.execute(text("SELECT 1"))  # toma la conexión antes de la largada
                except BaseException:
                    barrera.abort()
                    raise
                barrera.wait()
                return trabajo(sesion)

        with ThreadPoolExecutor(max_workers=total, thread_name_prefix="base-confirmada") as pool:
            futuros = [pool.submit(_hilo, trabajo) for trabajo in trabajos]

        excepciones = [e for futuro in futuros if (e := futuro.exception()) is not None]
        if excepciones:
            primera = next(
                (e for e in excepciones if not isinstance(e, threading.BrokenBarrierError)),
                excepciones[0],
            )
            tipos = Counter(type(e).__name__ for e in excepciones)
            primera.add_note(f"Fallaron {len(excepciones)} de {total} hilos: {dict(tipos)}")
            raise primera
        return [futuro.result() for futuro in futuros]

    def filas_nuevas(self) -> dict[str, int]:
        """Diferencia de filas de cada tabla respecto del inicio; solo las que cambiaron."""
        actuales = self._contar()
        return {
            nombre: actuales[nombre] - inicial
            for nombre, inicial in self._filas_iniciales.items()
            if actuales[nombre] != inicial
        }

    def limpiar(self) -> None:
        """Borra lo que el test confirmó: las filas con id mayor que el del inicio.

        No se usa TRUNCATE porque la base de tests es una sola para toda la corrida: guarda lo
        que siembran las migraciones (ciudades) y hay tests que suponen las demás tablas vacías.
        TRUNCATE ... CASCADE arrastraría tablas sin avisar y exige un bloqueo exclusivo. Borrar
        por id quita solo lo creado aquí, y las secuencias nunca retroceden. Es idempotente.
        """
        with self.engine.begin() as conexion:
            for tabla in self._tablas:
                if "id" in tabla.c:
                    conexion.execute(delete(tabla).where(tabla.c.id > self._ultimo_id[tabla.name]))

    def _contar(self) -> dict[str, int]:
        with self.engine.connect() as conexion:
            return {
                tabla.name: conexion.execute(select(func.count()).select_from(tabla)).scalar_one()
                for tabla in self._tablas
            }

    def _ultimos_ids(self) -> dict[str, int]:
        with self.engine.connect() as conexion:
            return {
                tabla.name: conexion.execute(
                    select(func.coalesce(func.max(tabla.c.id), 0))
                ).scalar_one()
                for tabla in self._tablas
                if "id" in tabla.c
            }


# Fixtures que envuelven la prueba en una transacción que se revierte: con ellas lo que se
# confirma en otra conexión no se vería, o se mezclaría con lo que `base_confirmada` borra.
_FIXTURES_CON_ROLLBACK = frozenset({"db", "client", "crear_usuario", "client_como"})


@pytest.fixture
def base_confirmada(
    request: pytest.FixtureRequest, engine_de_tests: Engine
) -> Iterator[BaseConfirmada]:
    """Sesiones que confirman de verdad, una por hilo, para pruebas de concurrencia (#129, RNF-17).

    A diferencia de `db`, lo confirmado lo ven las demás conexiones. Al terminar borra todo lo
    que el test confirmó (filas con id mayor que el inicial) y falla si alguna tabla no volvió a
    su conteo. No se combina con `db`, `client`, `crear_usuario` ni `client_como`.
    """
    mezcladas = _FIXTURES_CON_ROLLBACK & set(request.fixturenames)
    if mezcladas:
        pytest.fail(f"base_confirmada no se combina con {sorted(mezcladas)}", pytrace=False)
    # El pool por defecto (5 + 10) no alcanza para 50 hilos con una conexión cada uno.
    engine = create_engine(
        engine_de_tests.url, pool_size=CONEXIONES_SIMULTANEAS, max_overflow=0, pool_pre_ping=True
    )
    try:
        base = BaseConfirmada(engine)
        yield base
        base.limpiar()
        sobrantes = base.filas_nuevas()
    finally:
        engine.dispose()
    if sobrantes:
        raise AssertionError(f"La prueba dejó datos confirmados en la base de tests: {sobrantes}")
