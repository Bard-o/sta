"""Endpoints de catálogo y vista previa (HU-13, RF-12 a RF-16)."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import crear_vuelo

RUTA = "/api/v1/vuelos/vista-previa"


def cuerpo_vuelo(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "origen": "PEI",
        "destino": "MAD",
        "fecha_salida": "2099-01-15",
        "hora_salida": "10:00",
        "duracion_minutos": 600,
        "precio_economica": 2_450_000,
        "precio_primera": 6_900_000,
    }
    base.update(cambios)
    return base


def test_catalogo_publico(client: TestClient) -> None:
    """RF-12: GET /ciudades es público y devuelve las 37 ciudades."""
    respuesta = client.get("/api/v1/ciudades")

    assert respuesta.status_code == 200
    ciudades = respuesta.json()
    assert len(ciudades) == 37
    assert {"codigo", "nombre", "pais", "zona_horaria", "tipo", "imagen_url"} <= set(ciudades[0])


def test_vista_previa_calcula_tipo_capacidad_y_llegada(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-13: la vista previa devuelve lo que tendría el vuelo sin guardarlo."""
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(RUTA, json=cuerpo_vuelo())

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["tipo"] == "internacional"
    assert datos["origen"] == {
        "codigo": "PEI",
        "nombre": "Pereira",
        "zona_horaria": "America/Bogota",
    }
    assert datos["destino"]["codigo"] == "MAD"
    assert datos["salida"] == "2099-01-15T15:00:00Z"
    assert datos["llegada"] == "2099-01-16T01:00:00Z"
    assert datos["capacidad"] == {"primera": 50, "economica": 200, "total": 250}


def test_vista_previa_no_guarda_nada(db: Session, client_como: Callable[[Rol], TestClient]) -> None:
    """HU-13: la vista previa no inserta filas en vuelos."""
    admin = client_como(Rol.ADMIN)
    antes = db.scalar(select(func.count(Vuelo.id)))

    respuesta = admin.post(RUTA, json=cuerpo_vuelo())

    assert respuesta.status_code == 200
    assert db.scalar(select(func.count(Vuelo.id))) == antes


def test_vista_previa_rechaza_ruta_no_permitida(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-13 · RF-14: Manizales → Miami responde ruta_no_permitida."""
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(RUTA, json=cuerpo_vuelo(origen="MZL", destino="MIA"))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "ruta_no_permitida"
    assert "mensaje" in error
    assert "destino" in error["campos"]


def test_vista_previa_rechaza_ciudad_fuera_del_catalogo(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """RF-13: una ciudad que no está en el catálogo responde datos_invalidos."""
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(RUTA, json=cuerpo_vuelo(destino="ZZZ"))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "destino" in error["campos"]


def test_vista_previa_rechaza_salida_en_el_pasado(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-13 · RF-13: una salida en el pasado responde datos_invalidos."""
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(RUTA, json=cuerpo_vuelo(fecha_salida="2020-01-01"))

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert "fecha_salida" in error["campos"]


def test_vista_previa_rechaza_vuelo_duplicado(
    db: Session, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-13 · RF-16: mismo Pereira → Bogotá a las 06:00 responde vuelo_duplicado."""
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
    )
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(
        RUTA,
        json=cuerpo_vuelo(
            origen="PEI",
            destino="BOG",
            fecha_salida="2026-12-10",
            hora_salida="06:00",
            duracion_minutos=50,
        ),
    )

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "vuelo_duplicado"
    assert "hora_salida" in error["campos"]


def test_vista_previa_acepta_la_misma_ruta_veinte_minutos_despues(
    db: Session, client_como: Callable[[Rol], TestClient]
) -> None:
    """HU-13 · RF-16: otro Pereira → Bogotá a las 06:20 es aceptado."""
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
    )
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(
        RUTA,
        json=cuerpo_vuelo(
            origen="PEI",
            destino="BOG",
            fecha_salida="2026-12-10",
            hora_salida="06:20",
            duracion_minutos=50,
        ),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["salida"] == "2026-12-10T11:20:00Z"


def test_vista_previa_rechaza_duracion_y_precios_invalidos(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-13 · RF-13: duración 0 o 1440 y precios ≤ 0 responden datos_invalidos."""
    admin = client_como(Rol.ADMIN)

    casos = [
        ({"duracion_minutos": 0}, "duracion_minutos"),
        ({"duracion_minutos": -1}, "duracion_minutos"),
        ({"duracion_minutos": 1440}, "duracion_minutos"),
        ({"precio_economica": 0}, "precio_economica"),
        ({"precio_economica": -1}, "precio_economica"),
        ({"precio_primera": 0}, "precio_primera"),
        ({"precio_primera": -1}, "precio_primera"),
    ]
    for cambio, campo in casos:
        respuesta = admin.post(RUTA, json=cuerpo_vuelo(**cambio))
        assert respuesta.status_code == 422
        error = respuesta.json()["error"]
        assert error["codigo"] == "datos_invalidos"
        assert campo in error["campos"]


def test_vista_previa_muestra_el_horario_de_verano_de_madrid(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-13 · RF-15: julio de 2027 llega 15:00 a Madrid (UTC+2)."""
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(
        RUTA,
        json=cuerpo_vuelo(
            origen="BOG",
            destino="MAD",
            fecha_salida="2027-07-10",
            hora_salida="22:00",
        ),
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["salida"] == "2027-07-11T03:00:00Z"
    assert datos["llegada"] == "2027-07-11T13:00:00Z"


def test_vista_previa_muestra_el_horario_estandar_de_madrid(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-13 · RF-15: diciembre de 2027 llega 14:00 a Madrid (UTC+1)."""
    admin = client_como(Rol.ADMIN)

    respuesta = admin.post(
        RUTA,
        json=cuerpo_vuelo(
            origen="BOG",
            destino="MAD",
            fecha_salida="2027-12-10",
            hora_salida="22:00",
        ),
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["salida"] == "2027-12-11T03:00:00Z"
    assert datos["llegada"] == "2027-12-11T13:00:00Z"


def test_llegada_local_de_madrid_en_verano_e_invierno(
    client_como: Callable[[Rol], TestClient],
) -> None:
    """HU-13 · RF-15: el frontend muestra 15:00 y 14:00 en Madrid según la fecha."""
    admin = client_como(Rol.ADMIN)
    verano = datetime.fromisoformat(
        admin.post(
            RUTA,
            json=cuerpo_vuelo(
                origen="BOG", destino="MAD", fecha_salida="2027-07-10", hora_salida="22:00"
            ),
        ).json()["llegada"]
    )
    invierno = datetime.fromisoformat(
        admin.post(
            RUTA,
            json=cuerpo_vuelo(
                origen="BOG", destino="MAD", fecha_salida="2027-12-10", hora_salida="22:00"
            ),
        ).json()["llegada"]
    )

    local_verano = verano.astimezone(ZoneInfo("Europe/Madrid"))
    local_invierno = invierno.astimezone(ZoneInfo("Europe/Madrid"))
    assert (local_verano.date(), local_verano.hour) == (date(2027, 7, 11), 15)
    assert (local_invierno.date(), local_invierno.hour) == (date(2027, 12, 11), 14)
