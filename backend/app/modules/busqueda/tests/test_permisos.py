"""RNF-10, Apéndice B: la búsqueda es pública para todos los roles, también sin sesión.

Matriz del contrato en docs/api/iteracion-2.md: visitantes, clientes, administradores y root
reciben 200; nunca 401 ni 403.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.vuelos.tests.fabricas import crear_vuelo

IDA = datetime(2027, 4, 15, 15, 0, tzinfo=UTC)
REGRESO = datetime(2027, 4, 22, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize("rol", [None, *Rol], ids=lambda r: r or "visitante")
def test_la_busqueda_es_publica(
    rol: Rol | None,
    client: TestClient,
    client_como: Callable[[Rol], TestClient],
    db: Session,
) -> None:
    # RF-27, Apéndice B: buscar vuelos está permitido a visitantes, clientes, admin y root.
    ida = crear_vuelo(db, origen="PEI", destino="JFK", salida=IDA, duracion_minutos=330)
    crear_vuelo(db, origen="JFK", destino="CTG", salida=REGRESO)

    cliente_http = client_como(rol) if rol else client
    rutas = [
        "/api/v1/busqueda/vuelos?origen=PEI",
        f"/api/v1/busqueda/regresos?vuelo_ida_id={ida.id}&destino=CTG&fecha=2027-04-22",
    ]
    for ruta in rutas:
        respuesta = cliente_http.get(ruta)
        assert respuesta.status_code == 200, f"GET {ruta} como {rol}: {respuesta.text}"
