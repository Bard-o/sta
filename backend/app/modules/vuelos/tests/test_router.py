"""Endpoints de catálogo, vista previa y creación de vuelos (HU-13, RF-12 a RF-16)."""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST
from app.modules.auditoria import service as auditoria_service
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.noticias import service as noticias_service
from app.modules.noticias.models import Noticia
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import crear_vuelo

RUTA = "/api/v1/vuelos/vista-previa"
RUTA_CREAR = "/api/v1/vuelos"


def iniciar_sesion_admin(client: TestClient, crear_usuario: Callable[..., Any]) -> Any:
    """Crea un administrador y abre su sesión en el cliente. Devuelve el usuario."""
    usuario = crear_usuario(Rol.ADMIN)
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200, respuesta.text
    return usuario


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


# ---------- POST /vuelos (HU-13) ----------


def test_programar_vuelo_devuelve_201_con_el_vuelo_admin(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-13 · contrato: POST /vuelos devuelve 201 y el VueloAdmin del vuelo nuevo."""
    iniciar_sesion_admin(client, crear_usuario)

    respuesta = client.post(RUTA_CREAR, json=cuerpo_vuelo())

    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert re.fullmatch(r"STA-\d{5}", datos["codigo"])
    assert datos["estado"] == "programado"
    assert datos["origen"]["codigo"] == "PEI"
    assert datos["destino"]["codigo"] == "MAD"
    assert datos["salida"] == "2099-01-15T15:00:00Z"
    assert datos["llegada"] == "2099-01-16T01:00:00Z"
    assert datos["capacidad"] == {"primera": 50, "economica": 200, "total": 250}
    assert datos["ocupacion"] == {
        "primera": {"capacidad": 50, "vendidas": 0, "reservadas": 0, "disponibles": 50},
        "economica": {
            "capacidad": 200,
            "vendidas": 0,
            "reservadas": 0,
            "disponibles": 200,
        },
    }
    assert datos["reservas_activas"] == 0
    assert datos["tiquetes_vendidos"] == 0
    assert datos["editable"] is True
    assert datos["motivo_no_editable"] is None
    assert datos["cancelable"] is True
    assert datos["promociones"] == []


def test_programar_vuelo_publica_la_noticia_con_la_imagen_de_miami(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-13 · RF-22: Pereira → Miami genera la noticia y el elemento del carrusel."""
    iniciar_sesion_admin(client, crear_usuario)

    respuesta = client.post(
        RUTA_CREAR,
        json=cuerpo_vuelo(origen="PEI", destino="MIA", duracion_minutos=240),
    )

    assert respuesta.status_code == 201
    vuelo = db.scalars(select(Vuelo)).one()
    noticia = db.scalars(select(Noticia)).one()
    assert noticia.tipo == "vuelo"
    assert noticia.vigente is True
    assert noticia.vuelo_id == vuelo.id
    assert noticia.vuelo_codigo == vuelo.codigo
    assert noticia.origen_nombre == "Pereira"
    assert noticia.destino_codigo == "MIA"
    assert noticia.destino_nombre == "Miami"
    assert noticia.imagen_url == "/imagenes/ciudades/MIA.jpg"
    assert noticia.titulo == "Nuevo vuelo Pereira → Miami"


def test_la_creacion_queda_en_la_auditoria(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-13 · RF-26: la creación queda en la auditoría como vuelo.crear."""
    usuario = iniciar_sesion_admin(client, crear_usuario)

    respuesta = client.post(RUTA_CREAR, json=cuerpo_vuelo())

    assert respuesta.status_code == 201
    vuelo = db.scalars(select(Vuelo)).one()
    registro = db.scalars(select(RegistroAuditoria)).one()
    assert registro.usuario_id == usuario.id
    assert registro.accion == "vuelo.crear"
    assert registro.entidad == "vuelo"
    assert registro.entidad_id == vuelo.id
    assert registro.antes is None
    assert registro.despues is not None
    assert registro.despues["codigo"] == vuelo.codigo
    assert registro.despues["tipo"] == "internacional"
    assert registro.despues["origen"] == "PEI"
    assert registro.despues["destino"] == "MAD"
    assert registro.despues["salida"] == vuelo.salida.isoformat()
    assert registro.despues["precio_economica"] == 2_450_000
    assert registro.despues["estado"] == "programado"


def test_el_codigo_sale_de_la_secuencia_y_no_se_reutiliza(
    client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-13 · SUP-01: cada vuelo recibe su STA-nnnnn y el código no se repite."""
    iniciar_sesion_admin(client, crear_usuario)
    ruta_nacional = {
        "origen": "PEI",
        "destino": "BOG",
        "hora_salida": "06:00",
        "duracion_minutos": 50,
    }

    primero = client.post(RUTA_CREAR, json=cuerpo_vuelo(fecha_salida="2099-02-01", **ruta_nacional))
    segundo = client.post(RUTA_CREAR, json=cuerpo_vuelo(fecha_salida="2099-02-02", **ruta_nacional))

    assert primero.status_code == segundo.status_code == 201
    codigo_primero = primero.json()["codigo"]
    codigo_segundo = segundo.json()["codigo"]
    assert re.fullmatch(r"STA-\d{5}", codigo_primero)
    assert re.fullmatch(r"STA-\d{5}", codigo_segundo)
    assert codigo_segundo != codigo_primero
    assert int(codigo_segundo[4:]) > int(codigo_primero[4:])


@pytest.mark.parametrize(
    ("cambios", "estado", "codigo", "campo"),
    [
        ({"origen": "MZL", "destino": "MIA"}, 422, "ruta_no_permitida", "destino"),
        ({"origen": "MAD", "destino": "LHR"}, 422, "ruta_no_permitida", "destino"),
        ({"destino": "ZZZ"}, 422, "datos_invalidos", "destino"),
        ({"destino": "PEI"}, 422, "datos_invalidos", "destino"),
        ({"fecha_salida": "2020-01-01"}, 422, "datos_invalidos", "fecha_salida"),
        ({"duracion_minutos": 0}, 422, "datos_invalidos", "duracion_minutos"),
        ({"duracion_minutos": 1440}, 422, "datos_invalidos", "duracion_minutos"),
        ({"precio_economica": 0}, 422, "datos_invalidos", "precio_economica"),
        ({"precio_primera": -1}, 422, "datos_invalidos", "precio_primera"),
    ],
)
def test_guardar_aplica_las_mismas_validaciones_que_la_vista_previa(
    db: Session,
    client: TestClient,
    crear_usuario: Callable[..., Any],
    cambios: dict[str, object],
    estado: int,
    codigo: str,
    campo: str,
) -> None:
    """HU-13 · RF-13/RF-14: guardar rechaza exactamente lo mismo que la vista previa."""
    iniciar_sesion_admin(client, crear_usuario)
    cuerpo = cuerpo_vuelo(**cambios)

    previa = client.post(RUTA, json=cuerpo)
    guardar = client.post(RUTA_CREAR, json=cuerpo)

    assert guardar.status_code == previa.status_code == estado
    assert guardar.json()["error"]["codigo"] == previa.json()["error"]["codigo"] == codigo
    assert campo in guardar.json()["error"]["campos"]
    assert db.scalar(select(func.count(Vuelo.id))) == 0


def test_programar_vuelo_rechaza_duplicado_y_acepta_veinte_minutos_despues(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-13 · RF-16: el mismo Pereira → Bogotá a las 06:00 responde vuelo_duplicado."""
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2099, 1, 15, 11, 0, tzinfo=UTC),
    )
    iniciar_sesion_admin(client, crear_usuario)
    ruta = {
        "origen": "PEI",
        "destino": "BOG",
        "fecha_salida": "2099-01-15",
        "duracion_minutos": 50,
    }

    duplicado = client.post(RUTA_CREAR, json=cuerpo_vuelo(hora_salida="06:00", **ruta))
    despues = client.post(RUTA_CREAR, json=cuerpo_vuelo(hora_salida="06:20", **ruta))

    assert duplicado.status_code == 409
    error = duplicado.json()["error"]
    assert error["codigo"] == "vuelo_duplicado"
    assert "hora_salida" in error["campos"]
    assert despues.status_code == 201


def test_si_falla_la_noticia_no_queda_el_vuelo_ni_la_auditoria(
    db: Session,
    client: TestClient,
    crear_usuario: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-13 · RNF-17: si falla la noticia, se revierte también el vuelo y la auditoría."""
    iniciar_sesion_admin(client, crear_usuario)

    def fallar(*_: object, **__: object) -> None:
        raise RuntimeError("falla al publicar la noticia")

    monkeypatch.setattr(noticias_service, "publicar_noticia_vuelo", fallar)
    vuelos_antes = db.scalar(select(func.count(Vuelo.id)))
    auditorias_antes = db.scalar(select(func.count(RegistroAuditoria.id)))

    with pytest.raises(RuntimeError):
        client.post(RUTA_CREAR, json=cuerpo_vuelo())

    assert db.scalar(select(func.count(Vuelo.id))) == vuelos_antes
    assert db.scalar(select(func.count(RegistroAuditoria.id))) == auditorias_antes


def test_si_falla_la_auditoria_no_queda_el_vuelo_ni_la_noticia(
    db: Session,
    client: TestClient,
    crear_usuario: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU-13 · RNF-17: si falla la auditoría, se revierte también el vuelo y su noticia."""
    iniciar_sesion_admin(client, crear_usuario)

    def fallar(*_: object, **__: object) -> None:
        raise RuntimeError("falla al registrar la auditoría")

    monkeypatch.setattr(auditoria_service, "registrar", fallar)
    vuelos_antes = db.scalar(select(func.count(Vuelo.id)))
    noticias_antes = db.scalar(select(func.count(Noticia.id)))

    with pytest.raises(RuntimeError):
        client.post(RUTA_CREAR, json=cuerpo_vuelo())

    assert db.scalar(select(func.count(Vuelo.id))) == vuelos_antes
    assert db.scalar(select(func.count(Noticia.id))) == noticias_antes
