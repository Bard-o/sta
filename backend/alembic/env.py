"""Entorno de Alembic: descubre los models.py de todos los módulos."""

import importlib
import pkgutil
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app import modules
from app.core.config import get_settings
from app.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importa app/modules/<modulo>/models.py de cada módulo para registrar sus tablas.
for modulo in pkgutil.iter_modules(modules.__path__):
    if modulo.ispkg:
        try:
            importlib.import_module(f"app.modules.{modulo.name}.models")
        except ModuleNotFoundError as exc:
            if exc.name != f"app.modules.{modulo.name}.models":
                raise

target_metadata = Base.metadata


def _url() -> str:
    # Los tests pasan su propia URL con config.attributes["url"].
    return config.attributes.get("url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
