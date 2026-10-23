"""Archivos que suben los usuarios (imagen de perfil, HU-01 y HU-07), guardados por clave.

Viven en ARCHIVOS_DIR (por defecto /data/archivos, el volumen `archivos` de docker compose):
sobreviven a `docker compose down` y a reconstruir la imagen; `docker compose down -v` los borra.

Uso desde el service.py de un módulo:

    from app.core import archivos

    archivos.guardar(f"perfiles/{usuario.id}", contenido)   # crea o reemplaza (escritura atómica)
    contenido = archivos.leer(f"perfiles/{usuario.id}")     # NoEncontrado (404) si no hay
    archivos.borrar(f"perfiles/{usuario.id}")               # True si existía, False si no

- La clave la arma el módulo con datos propios (p. ej. el id), nunca con texto del cliente.
  Formato: 1 a 4 segmentos separados por "/", cada uno con [a-z0-9_-] (máx. 64), sin empezar
  por "_" ni "-"; sin puntos ni extensiones. Una clave inválida lanza ValueError (error de
  programación).
- core no valida tipo ni tamaño ni guarda el tipo de contenido: eso es del módulo (usuarios
  valida JPG/PNG de máx. 2 MB y deduce el media type por la firma de los bytes o lo guarda en
  su modelo).
- En los tests, la fixture autouse `archivos_dir` (app/core/testing.py) apunta a un tmp_path.
"""

import os
import re
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import NoEncontrado

_SEGMENTO = r"[a-z0-9][a-z0-9_-]{0,63}"
_CLAVE = re.compile(rf"{_SEGMENTO}(?:/{_SEGMENTO}){{0,3}}")


def _ruta(clave: str) -> Path:
    """Ruta absoluta de la clave dentro de la raíz; ValueError si no es válida o se sale."""
    if not isinstance(clave, str) or not _CLAVE.fullmatch(clave):
        raise ValueError(f"Clave de archivo inválida: {clave!r}")
    raiz = Path(get_settings().archivos_dir).resolve()
    ruta = (raiz / clave).resolve()
    # Cubre un enlace simbólico (en un directorio o en el propio archivo) que apunte afuera.
    if not ruta.is_relative_to(raiz) or not ruta.parent.resolve().is_relative_to(raiz):
        raise ValueError(f"Clave de archivo inválida: {clave!r}")
    return ruta


def guardar(clave: str, contenido: bytes) -> None:
    """Guarda `contenido` en la clave; si ya había un archivo, lo reemplaza de forma atómica."""
    ruta = _ruta(clave)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def leer(clave: str) -> bytes:
    """Bytes del archivo de la clave. Lanza NoEncontrado (404 no_encontrado) si no existe."""
    try:
        return _ruta(clave).read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        raise NoEncontrado() from None


def borrar(clave: str) -> bool:
    """Borra el archivo de la clave. Devuelve False si no existía (es idempotente)."""
    try:
        _ruta(clave).unlink()
    except FileNotFoundError:
        return False
    return True
