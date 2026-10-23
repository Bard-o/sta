"""Configuración leída de variables de entorno (archivo .env vía docker compose)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    test_database_url: str | None = None

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    session_minutes_cliente: int = 30
    session_minutes_staff: int = 15
    cookie_name: str = "sta_sesion"
    cookie_secure: bool = True

    root_username: str = "root"
    root_password: str | None = None

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    mail_from: str = "AVIANCO <no-responder@avianco.test>"
    frontend_url: str = "http://localhost:5173"

    # False en los tests: el hilo del planificador no arranca.
    planificador_activo: bool = True
    # Archivos que suben los usuarios (imagen de perfil). Fuera de /app, que es el código montado;
    # en docker compose es el volumen con nombre `archivos`.
    archivos_dir: Path = Path("/data/archivos")


@lru_cache
def get_settings() -> Settings:
    return Settings()
