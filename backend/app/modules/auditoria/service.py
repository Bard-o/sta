"""Interfaz pública del módulo auditoría. Otros módulos solo llaman a estas funciones.

Los registros no se modifican ni se borran (RF-26, RNF-16). La consulta (HU-50) llega en la
iteración 4.
"""

import json
import unicodedata
from typing import Any, Literal, get_args

from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos
from app.modules.auditoria.models import RegistroAuditoria

AccionAuditada = Literal[
    "vuelo.crear",
    "vuelo.editar",
    "vuelo.cancelar",
    "promocion.crear",
    "administrador.crear",
    "administrador.desactivar",
    "administrador.reactivar",
]
EntidadAuditada = Literal["vuelo", "promocion", "usuario"]

_ACCIONES_AUDITADAS = frozenset(get_args(AccionAuditada))
_ENTIDADES_AUDITADAS = frozenset(get_args(EntidadAuditada))

# Claves que podrían llevar una contraseña. Se comparan sin tildes y en minúscula.
_RAICES_CONTRASENA = ("contrasena", "password", "passwd", "pwd", "secret", "secreto")
# `confirmacion` repite la contraseña nueva en los schemas de usuarios (HU-05, HU-06, HU-12).
_CLAVES_CONTRASENA = frozenset({"clave", "confirmacion"})


def _normalizar(clave: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", clave).encode("ascii", "ignore").decode()
    return sin_tildes.strip().lower()


def _es_clave_de_contrasena(clave: object) -> bool:
    normalizada = _normalizar(str(clave))
    return normalizada in _CLAVES_CONTRASENA or any(
        raiz in normalizada for raiz in _RAICES_CONTRASENA
    )


def _revisar_claves(valor: Any, campo: str) -> None:
    if isinstance(valor, dict):
        for clave, contenido in valor.items():
            if _es_clave_de_contrasena(clave):
                raise DatosInvalidos(campos={campo: "No puede contener contraseñas."})
            _revisar_claves(contenido, campo)
    elif isinstance(valor, (list, tuple)):
        for elemento in valor:
            _revisar_claves(elemento, campo)


def _validar_detalle(valor: dict[str, Any] | None, campo: str) -> None:
    if valor is None:
        return
    if not isinstance(valor, dict):
        raise DatosInvalidos(campos={campo: "Debe ser un objeto JSON."})
    _revisar_claves(valor, campo)
    try:
        json.dumps(valor, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise DatosInvalidos(
            campos={campo: "Solo admite valores serializables en JSON (fechas en ISO 8601)."}
        ) from None


def registrar(
    db: Session,
    *,
    usuario_id: int,
    accion: AccionAuditada,
    entidad: EntidadAuditada,
    entidad_id: int,
    antes: dict[str, Any] | None = None,
    despues: dict[str, Any] | None = None,
) -> None:
    """Registra una acción administrativa con la fecha y hora actuales en UTC.

    `antes` y `despues` llevan solo valores serializables en JSON (fechas en ISO 8601) y nunca
    claves de contraseña. No hace commit: el registro entra en la misma transacción que la
    acción, o no entra (RF-26, RNF-17).
    """
    if accion not in _ACCIONES_AUDITADAS:
        raise DatosInvalidos(campos={"accion": "No es una acción auditable."})
    if entidad not in _ENTIDADES_AUDITADAS:
        raise DatosInvalidos(campos={"entidad": "No es una entidad auditable."})
    _validar_detalle(antes, "antes")
    _validar_detalle(despues, "despues")

    db.add(
        RegistroAuditoria(
            usuario_id=usuario_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            antes=antes,
            despues=despues,
        )
    )
    db.flush()
