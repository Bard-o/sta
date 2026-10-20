"""Crea el usuario root desde el .env si todavía no existe (RF-01).

docker compose run --rm backend uv run python -m app.seed
"""

import logging

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.usuarios import service as usuarios_service

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")


def main() -> None:
    settings = get_settings()
    if not settings.root_password:
        raise SystemExit("Falta ROOT_PASSWORD en el .env.")
    with SessionLocal() as db:
        creado = usuarios_service.asegurar_root(db, settings.root_username, settings.root_password)
    if creado:
        logger.info("Usuario root «%s» creado.", settings.root_username)
    else:
        logger.info("El usuario root ya existe; no se modifica.")


if __name__ == "__main__":
    main()
