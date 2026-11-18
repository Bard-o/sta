"""Ayudas de los tests HTTP del monedero (HU-28 a HU-31).

Crean clientes con sesión iniciada y tarjetas por la API, para probar los endpoints tal como
los consume el frontend. Los números de prueba siempre pasan Luhn.
"""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.monedero import service

RUTA_MONEDERO = "/api/v1/monedero"
RUTA_MOVIMIENTOS = "/api/v1/monedero/movimientos"
RUTA_TARJETAS = "/api/v1/monedero/tarjetas"
RUTA_RECARGAS = "/api/v1/monedero/recargas"

# Números de prueba válidos para Luhn (HU-28).
VISA = "4242424242424242"
MASTERCARD = "5555555555554444"
AMEX = "378282246310005"
DINERS = "30569309025904"


def crear_cliente(db: Session, crear_usuario: Callable[..., Any], nombre: str) -> Any:
    """Cliente verificado con su correo, listo para iniciar sesión."""
    usuario = crear_usuario(Rol.CLIENTE, nombre_usuario=nombre, email=f"{nombre}@example.com")
    usuario.email_verificado = True
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


def tarjeta_entrada(**cambios: object) -> dict[str, object]:
    """Cuerpo de `TarjetaEntrada` con datos válidos; `cambios` pisa lo que haga falta."""
    datos: dict[str, object] = {
        "tipo": "credito",
        "titular": "LAURA GOMEZ RIOS",
        "numero": VISA,
        "vencimiento": "08/28",
        "cvv": "123",
    }
    datos.update(cambios)
    return datos


def registrar_tarjeta(cliente_http: TestClient, **cambios: object) -> dict[str, Any]:
    """Registra una tarjeta por la API y devuelve la respuesta del contrato."""
    respuesta = cliente_http.post(RUTA_TARJETAS, json=tarjeta_entrada(**cambios))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def error_de(respuesta: Any) -> dict[str, Any]:
    """Cuerpo de error del formato único de la API."""
    return respuesta.json()["error"]


def numero_con_luhn(prefijo: str) -> str:
    """Completa `prefijo` con el dígito de control de Luhn (RNF-12 en HU-28)."""
    for digito in "0123456789":
        candidato = f"{prefijo}{digito}"
        if service.luhn_valido(candidato):
            return candidato
    raise AssertionError(f"No hay un número válido con el prefijo {prefijo}.")
