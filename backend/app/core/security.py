"""Contraseñas (RNF-08) y tokens de sesión (JWT)."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings


class Rol(StrEnum):
    ROOT = "root"
    ADMIN = "admin"
    CLIENTE = "cliente"


# Argon2id con los parámetros recomendados por argon2-cffi (RFC 9106, perfil de baja memoria).
_hasher = PasswordHasher()

# Hash de relleno para que una cuenta inexistente tarde lo mismo que una contraseña errada.
_HASH_RELLENO = _hasher.hash("relleno-para-tiempo-constante")

_POLITICA = re.compile(r"^(?=.*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])(?=.*\d).{8,}$")


def hash_contrasena(contrasena: str) -> str:
    return _hasher.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_guardado: str | None) -> bool:
    """Compara en tiempo constante. Con `hash_guardado=None` igual gasta el tiempo de un hash."""
    try:
        return _hasher.verify(hash_guardado or _HASH_RELLENO, contrasena) and bool(hash_guardado)
    except (VerificationError, InvalidHashError):
        return False


def cumple_politica_contrasena(contrasena: str) -> bool:
    """RNF-08: al menos 8 caracteres, una letra y un número."""
    return bool(_POLITICA.match(contrasena))


MENSAJE_POLITICA_CONTRASENA = "Debe tener al menos 8 caracteres, con letras y números."


@dataclass(frozen=True)
class DatosToken:
    usuario_id: int
    rol: Rol
    version_sesion: int
    emitido_en: datetime


def minutos_de_sesion(rol: Rol) -> int:
    """RNF-14: 30 minutos de inactividad para clientes, 15 para administradores y root."""
    settings = get_settings()
    if rol == Rol.CLIENTE:
        return settings.session_minutes_cliente
    return settings.session_minutes_staff


def crear_token(usuario_id: int, rol: Rol, version_sesion: int) -> str:
    settings = get_settings()
    ahora = datetime.now(UTC)
    payload = {
        "sub": str(usuario_id),
        "rol": rol.value,
        "sv": version_sesion,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos_de_sesion(rol)),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def leer_token(token: str) -> DatosToken | None:
    """Devuelve los datos del token o None si es inválido o venció."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
        return DatosToken(
            usuario_id=int(payload["sub"]),
            rol=Rol(payload["rol"]),
            version_sesion=int(payload["sv"]),
            emitido_en=datetime.fromtimestamp(payload["iat"], UTC),
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
