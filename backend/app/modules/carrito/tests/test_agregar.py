"""HU-22: agregar vuelos al carrito (RF-30, RF-32, RF-33, SUP-15)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.carrito.tests.apoyo import (
    RUTA_CARRITO,
    RUTA_SELECCIONES,
    agregar,
    crear_cliente,
    entrar,
    error_de,
    tramo,
)
from app.modules.reservas.models import Tiquete
from app.modules.reservas.tests.fabricas import crear_compra, crear_reserva
from app.modules.vuelos.tests.fabricas import crear_vuelo

SALIDA = datetime(2027, 4, 15, 11, 0, tzinfo=UTC)


def test_hu22_la_seleccion_sigue_en_el_carrito_despues_de_cerrar_sesion(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22: una selección agregada sigue en el carrito tras cerrar y volver a entrar."""
    cliente = crear_cliente(db, crear_usuario, "cliente_persistente")
    vuelo = crear_vuelo(db, salida=SALIDA)
    cliente_http = entrar(client, cliente)

    creada = agregar(cliente_http, [tramo(vuelo.id)], viajeros=2)
    assert creada.status_code == 201, creada.text
    assert cliente_http.post("/api/v1/auth/logout").status_code == 204

    entrar(client, cliente)
    carrito = client.get(RUTA_CARRITO)
    assert carrito.status_code == 200
    assert [seleccion["id"] for seleccion in carrito.json()["selecciones"]] == [creada.json()["id"]]
    assert carrito.json()["cantidad"] == 1


def test_hu22_si_la_clase_esta_agotada_no_agrega_y_responde_clase_agotada(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22 · RF-33: primera con una sola silla no admite dos viajeros."""
    cliente = crear_cliente(db, crear_usuario, "cliente_agotada")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_primera=1)
    cliente_http = entrar(client, cliente)

    respuesta = agregar(cliente_http, [tramo(vuelo.id, "primera")], viajeros=2)

    assert respuesta.status_code == 409
    assert error_de(respuesta)["codigo"] == "clase_agotada"
    assert error_de(respuesta)["mensaje"] == "No quedan sillas suficientes en esta clase."
    assert cliente_http.get(RUTA_CARRITO).json()["selecciones"] == []


def test_hu22_con_tres_comprados_y_dos_reservados_no_agrega_otro(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22 · RF-32: 3 comprados + 2 reservados ya llegan al máximo de 5 tiquetes."""
    cliente = crear_cliente(db, crear_usuario, "cliente_lleno")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_compra(db, cliente.id, vuelo, cantidad=3)
    crear_reserva(db, cliente.id, vuelo, cantidad=2)
    cliente_http = entrar(client, cliente)

    respuesta = agregar(cliente_http, [tramo(vuelo.id)], viajeros=1)

    assert respuesta.status_code == 409
    assert error_de(respuesta)["codigo"] == "limite_tiquetes"
    assert "campos" not in error_de(respuesta)
    assert cliente_http.get(RUTA_CARRITO).json()["selecciones"] == []


def test_rf32_al_cancelar_un_tiquete_se_puede_agregar_otro(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """RF-32: un tiquete cancelado libera cupo y el cliente puede volver a agregar."""
    cliente = crear_cliente(db, crear_usuario, "cliente_cancelado")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_compra(db, cliente.id, vuelo, cantidad=5)
    tiquete = db.scalar(select(Tiquete).where(Tiquete.vuelo_id == vuelo.id).limit(1))
    assert tiquete is not None
    tiquete.estado = "cancelado"
    db.flush()
    cliente_http = entrar(client, cliente)

    assert agregar(cliente_http, [tramo(vuelo.id)], viajeros=1).status_code == 201


def test_hu22_un_trayecto_completo_devuelve_dos_tramos_y_su_subtotal(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22 · RF-40: ida y regreso viajan como dos tramos de una sola selección."""
    cliente = crear_cliente(db, crear_usuario, "cliente_completo")
    ida = crear_vuelo(db, origen="PEI", destino="BOG", salida=SALIDA)
    regreso = crear_vuelo(
        db, origen="BOG", destino="PEI", salida=datetime(2027, 4, 16, 9, 0, tzinfo=UTC)
    )
    cliente_http = entrar(client, cliente)

    respuesta = agregar(cliente_http, [tramo(ida.id), tramo(regreso.id, "primera")], viajeros=2)

    assert respuesta.status_code == 201, respuesta.text
    seleccion = respuesta.json()
    assert [item["vuelo"]["id"] for item in seleccion["tramos"]] == [ida.id, regreso.id]
    assert [item["clase"] for item in seleccion["tramos"]] == ["economica", "primera"]
    assert seleccion["subtotal"] == (280_000 + 750_000) * 2
    assert seleccion["avisos"] == []
    assert seleccion["confirmable"] is True


def test_hu22_un_regreso_que_no_sale_del_destino_de_la_ida_responde_regreso_invalido(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22 · RF-28: el regreso debe salir del destino de la ida y después de su llegada."""
    cliente = crear_cliente(db, crear_usuario, "cliente_regreso")
    ida = crear_vuelo(db, origen="PEI", destino="BOG", salida=SALIDA)
    otro = crear_vuelo(
        db, origen="PEI", destino="BOG", salida=datetime(2027, 4, 16, 9, 0, tzinfo=UTC)
    )
    cliente_http = entrar(client, cliente)

    respuesta = agregar(cliente_http, [tramo(ida.id), tramo(otro.id)])

    assert respuesta.status_code == 422
    assert error_de(respuesta)["codigo"] == "regreso_invalido"
    assert (
        "Elige un regreso que salga después de tu llegada."
        in error_de(respuesta)["campos"]["tramos.1.vuelo_id"]
    )


def test_hu22_un_vuelo_cancelado_no_se_agrega(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22: un vuelo cancelado responde `vuelo_no_disponible` con el tramo en `campos`."""
    cliente = crear_cliente(db, crear_usuario, "cliente_cancelado_vuelo")
    vuelo = crear_vuelo(db, salida=SALIDA, estado="cancelado")
    cliente_http = entrar(client, cliente)

    respuesta = agregar(cliente_http, [tramo(vuelo.id)])

    assert respuesta.status_code == 409
    assert error_de(respuesta)["codigo"] == "vuelo_no_disponible"
    assert (
        error_de(respuesta)["campos"]["tramos.0.vuelo_id"]
        == "El vuelo no existe o ya no está programado."
    )


def test_hu22_un_vuelo_pasado_de_plazo_no_se_agrega(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22 · SUP-07: un nacional que sale en media hora ya cerró su venta."""
    cliente = crear_cliente(db, crear_usuario, "cliente_plazo")
    vuelo = crear_vuelo(db, salida=datetime.now(UTC) + timedelta(minutes=30))
    cliente_http = entrar(client, cliente)

    respuesta = agregar(cliente_http, [tramo(vuelo.id)])

    assert respuesta.status_code == 409
    assert error_de(respuesta)["codigo"] == "fuera_de_plazo"
    assert error_de(respuesta)["campos"]["tramos.0.vuelo_id"] == (
        "Ya no se puede reservar ni comprar."
    )


def test_hu22_el_limite_no_cuenta_otras_selecciones_del_carrito(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22: el límite compara tiquetes activos, no las otras selecciones del carrito."""
    cliente = crear_cliente(db, crear_usuario, "cliente_dos_selecciones")
    vuelo = crear_vuelo(db, salida=SALIDA)
    cliente_http = entrar(client, cliente)

    assert agregar(cliente_http, [tramo(vuelo.id)], viajeros=5).status_code == 201
    assert agregar(cliente_http, [tramo(vuelo.id)], viajeros=5).status_code == 201
    assert cliente_http.get(RUTA_CARRITO).json()["cantidad"] == 2


def test_hu22_agregar_no_crea_tiquetes_ni_cambia_la_disponibilidad(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """SUP-15: el carrito no bloquea sillas; eso pasa al iniciar la compra."""
    cliente = crear_cliente(db, crear_usuario, "cliente_sin_bloqueo")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_economica=3)
    cliente_http = entrar(client, cliente)

    respuesta = agregar(cliente_http, [tramo(vuelo.id)], viajeros=2)

    assert respuesta.status_code == 201
    assert respuesta.json()["tramos"][0]["disponibles"] == 3
    assert db.scalar(select(func.count(Tiquete.id)).where(Tiquete.vuelo_id == vuelo.id)) == 0


def test_hu22_el_cuerpo_valida_los_topes_tecnicos(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-22: tramos vacío o viajeros fuera del rango técnico responden `datos_invalidos`."""
    cliente = crear_cliente(db, crear_usuario, "cliente_invalido")
    vuelo = crear_vuelo(db, salida=SALIDA)
    cliente_http = entrar(client, cliente)

    sin_tramos = cliente_http.post(RUTA_SELECCIONES, json={"tramos": [], "viajeros": 1})
    muchos_viajeros = cliente_http.post(
        RUTA_SELECCIONES, json={"tramos": [tramo(vuelo.id)], "viajeros": 21}
    )

    assert sin_tramos.status_code == 422
    assert error_de(sin_tramos)["codigo"] == "datos_invalidos"
    assert muchos_viajeros.status_code == 422
    assert error_de(muchos_viajeros)["codigo"] == "datos_invalidos"
