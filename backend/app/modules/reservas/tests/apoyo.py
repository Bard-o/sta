"""Ayudas compartidas por los tests de reservas, compras y vencimiento.

Un cliente de prueba necesita el perfil completo (HU-07) y el correo verificado (HU-02); las
fábricas de `fabricas.py` preparan transacciones ya existentes, mientras que estas funciones
arman los cuerpos de la API para entrar por el service o por el endpoint.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from itertools import count
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.reservas.models import Tiquete, Tramo, Transaccion
from app.modules.reservas.schemas import ViajeEntrada
from app.modules.vuelos.models import Vuelo

AHORA = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
SALIDA = AHORA + timedelta(days=3)

# El documento de la cuenta es único por rol (índice de usuarios); el de los viajeros no.
_DOCUMENTOS_DE_CUENTA = count(10_000_000)


def cliente_con_perfil(
    db: Session,
    crear_usuario: Callable[..., Any],
    *,
    verificado: bool = True,
    **cambios: Any,
) -> Any:
    """Cliente con el perfil completo, como lo deja HU-07, y el correo en el estado pedido."""
    nombre = cambios.pop("nombre_usuario", "cliente_reserva")
    correo = cambios.pop("email", f"{nombre}@example.com")
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario=nombre, email=correo, **cambios)
    cliente.tipo_documento = "CC"
    cliente.numero_documento = str(next(_DOCUMENTOS_DE_CUENTA))
    cliente.nombres = "Cliente"
    cliente.apellidos = "De Prueba"
    cliente.fecha_nacimiento = date(1990, 1, 1)
    cliente.lugar_nacimiento = "Pereira, Risaralda"
    cliente.direccion_facturacion = "Cra. 7 # 19-28, Pereira"
    cliente.genero = "otro"
    cliente.email_verificado = verificado
    db.flush()
    return cliente


def cliente_verificado(db: Session, crear_usuario: Callable[..., Any], **cambios: Any) -> Any:
    return cliente_con_perfil(db, crear_usuario, verificado=True, **cambios)


def viajero(
    numero_documento: str = "1020304050",
    *,
    clases: tuple[str, ...] = ("economica",),
    fecha_nacimiento: date = date(1990, 1, 1),
    nombres: str = "Ana",
    apellidos: str = "Pérez",
    email: str = "ana@example.com",
) -> dict[str, Any]:
    """Viajero válido para el cuerpo de `POST /reservas`."""
    return {
        "tipo_documento": "CC",
        "numero_documento": numero_documento,
        "nombres": nombres,
        "apellidos": apellidos,
        "fecha_nacimiento": fecha_nacimiento.isoformat(),
        "genero": "femenino",
        "telefono": "3001234567",
        "email": email,
        "contacto_nombre": "Carlos Pérez",
        "contacto_telefono": "3007654321",
        "clases": list(clases),
    }


def entrada(vuelos: list[Vuelo], viajeros: list[dict[str, Any]] | None = None) -> ViajeEntrada:
    """Cuerpo de la API con una clase por tramo para el viajero por defecto."""
    if viajeros is None:
        viajeros = [viajero(clases=tuple("economica" for _ in vuelos))]
    return ViajeEntrada.model_validate(
        {
            "tramos": [{"vuelo_id": vuelo.id} for vuelo in vuelos],
            "viajeros": viajeros,
        }
    )


def tiquetes_de(db: Session, transaccion: Transaccion) -> list[Tiquete]:
    """Tiquetes de la transacción ordenados por silla."""
    return list(
        db.scalars(
            select(Tiquete)
            .join(Tramo, Tiquete.tramo_id == Tramo.id)
            .where(Tramo.transaccion_id == transaccion.id)
            .order_by(Tiquete.numero_silla)
        )
    )
