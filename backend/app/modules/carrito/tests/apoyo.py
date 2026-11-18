"""Ayudas de los tests HTTP del carrito (HU-22, HU-23).

Crean clientes con sesión iniciada y arman los cuerpos del contrato para probar los
endpoints tal como los consume el frontend.
"""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST

RUTA_CARRITO = "/api/v1/carrito"
RUTA_SELECCIONES = "/api/v1/carrito/selecciones"


def crear_cliente(db: Session, crear_usuario: Callable[..., Any], nombre: str) -> Any:
    """Cliente listo para iniciar sesión; el carrito no exige correo verificado (HU-22)."""
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario=nombre, email=f"{nombre}@example.com")
    db.flush()
    return usuario


def entrar(client: TestClient, usuario: Any) -> TestClient:
    """Inicia sesión en `client` con el usuario dado (cookie httpOnly)."""
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200, respuesta.text
    return client


def error_de(respuesta: Any) -> dict[str, Any]:
    """Cuerpo de error del formato único: `{"codigo", "mensaje", "campos"}`."""
    return respuesta.json()["error"]


def tramo(vuelo_id: int, clase: str = "economica") -> dict[str, object]:
    """Un tramo del cuerpo de `SeleccionEntrada`."""
    return {"vuelo_id": vuelo_id, "clase": clase}


def agregar(cliente_http: TestClient, tramos: list[dict[str, object]], viajeros: int = 1) -> Any:
    """POST de una selección del carrito."""
    return cliente_http.post(RUTA_SELECCIONES, json={"tramos": tramos, "viajeros": viajeros})
