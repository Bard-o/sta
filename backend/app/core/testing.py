"""Fixtures de pytest compartidas por todos los módulos (se cargan desde conftest.py).

- `db`: sesión sobre la base de datos de tests; todo lo que haga el test se deshace al final.
- `client`: TestClient de la API que usa esa misma sesión.
- `crear_usuario`: crea un usuario con rol y contraseña dados.
- `client_como`: TestClient con la sesión iniciada para un rol.
- `_sin_planificador_real` (automática): apaga el hilo del planificador en todos los tests.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import Rol
from app.main import app

CONTRASENA_TEST = "Clave1234"
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
    ) -> Any:
        nombre = nombre_usuario or f"{rol.value}_test"
        return usuarios_service.crear_usuario(
            db,
            nombre_usuario=nombre,
            contrasena=contrasena,
            rol=rol,
            email=email,
            activo=activo,
        )

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
