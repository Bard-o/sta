"""Interfaz pública del módulo auditoría. Otros módulos solo llaman a estas funciones.

Los registros no se modifican ni se borran (RF-26, RNF-16). La consulta (HU-50) llega en la
iteración 4.
"""

from typing import Any, Literal

from sqlalchemy.orm import Session

AccionAuditada = Literal[
    "vuelo.crear",
    "vuelo.editar",
    "vuelo.cancelar",
    "promocion.crear",
    "administrador.crear",
    "administrador.desactivar",
    "administrador.reactivar",
]


def registrar(
    db: Session,
    *,
    usuario_id: int,
    accion: AccionAuditada,
    entidad: Literal["vuelo", "promocion", "usuario"],
    entidad_id: int,
    antes: dict[str, Any] | None = None,
    despues: dict[str, Any] | None = None,
) -> None:
    """Registra una acción administrativa con la fecha y hora actuales en UTC.

    `antes` y `despues` llevan solo valores serializables en JSON (fechas en ISO 8601). No hace
    commit: el registro entra en la misma transacción que la acción, o no entra.
    """
    raise NotImplementedError("RF-26")
