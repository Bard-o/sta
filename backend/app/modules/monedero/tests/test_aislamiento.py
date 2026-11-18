"""Aislamiento entre clientes del monedero (HU-28 a HU-31)."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.monedero.tests.apoyo import (
    RUTA_MONEDERO,
    RUTA_RECARGAS,
    RUTA_TARJETAS,
    crear_cliente,
    entrar,
    error_de,
    registrar_tarjeta,
)


def test_un_cliente_no_ve_ni_usa_las_tarjetas_de_otro(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-28 a HU-31: un id ajeno responde 404 `no_encontrado`, igual que uno inexistente."""
    duena = crear_cliente(db, crear_usuario, "duena_de_la_tarjeta")
    tarjeta = registrar_tarjeta(entrar(client, duena))

    otro = crear_cliente(db, crear_usuario, "otro_cliente_del_monedero")
    cliente_http = entrar(client, otro)

    assert cliente_http.get(RUTA_TARJETAS).json() == []
    eliminar = cliente_http.delete(f"{RUTA_TARJETAS}/{tarjeta['id']}")
    assert eliminar.status_code == 404
    assert error_de(eliminar)["mensaje"] == "La tarjeta no existe."
    recargar = cliente_http.post(
        RUTA_RECARGAS, json={"tarjeta_id": tarjeta["id"], "valor": 500_000}
    )
    assert recargar.status_code == 404
    assert error_de(recargar)["codigo"] == "no_encontrado"
    assert cliente_http.get(RUTA_MONEDERO).json() == {"saldo": 0}

    # La tarjeta y el saldo de la dueña siguen intactos.
    cliente_http = entrar(client, duena)
    assert [item["id"] for item in cliente_http.get(RUTA_TARJETAS).json()] == [tarjeta["id"]]
    assert cliente_http.get(RUTA_MONEDERO).json() == {"saldo": 0}
