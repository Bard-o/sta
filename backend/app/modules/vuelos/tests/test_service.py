"""Validaciones y cálculos compartidos del módulo (HU-13, RF-12 a RF-16)."""

import re
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos
from app.core.security import Rol
from app.modules.vuelos import service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.schemas import VueloEntrada
from app.modules.vuelos.tests.fabricas import crear_vuelo


def datos_vuelo(**cambios: object) -> VueloEntrada:
    base: dict[str, object] = {
        "origen": "PEI",
        "destino": "MAD",
        "fecha_salida": date(2099, 1, 15),
        "hora_salida": time(10, 0),
        "duracion_minutos": 600,
        "precio_economica": 2_450_000,
        "precio_primera": 6_900_000,
    }
    base.update(cambios)
    return VueloEntrada(**base)


@pytest.mark.parametrize(
    ("origen", "destino", "tipo"),
    [
        ("PEI", "MAD", "internacional"),
        ("MAD", "CTG", "internacional"),
        ("BOG", "LHR", "internacional"),
        ("MDE", "JFK", "internacional"),
        ("CLO", "EZE", "internacional"),
        ("CTG", "MIA", "internacional"),
        ("MIA", "BOG", "internacional"),
        ("PEI", "BOG", "nacional"),
        ("BOG", "MZL", "nacional"),
    ],
)
def test_rutas_permitidas(db: Session, origen: str, destino: str, tipo: str) -> None:
    """HU-13 · RF-14: Pereira → Madrid y Madrid → Cartagena se aceptan."""
    calculado = service.validar_vuelo(db, datos_vuelo(origen=origen, destino=destino))

    assert calculado.tipo == tipo
    assert calculado.origen.codigo == origen
    assert calculado.destino.codigo == destino


@pytest.mark.parametrize(
    ("origen", "destino"),
    [
        ("MZL", "MIA"),
        ("MAD", "LHR"),
        ("MIA", "MAD"),
        ("MAD", "MZL"),
    ],
)
def test_rutas_prohibidas(db: Session, origen: str, destino: str) -> None:
    """HU-13 · RF-14: Manizales → Miami y Madrid → Londres se rechazan."""
    with pytest.raises(service.RutaNoPermitida) as error:
        service.validar_vuelo(db, datos_vuelo(origen=origen, destino=destino))

    assert error.value.codigo == "ruta_no_permitida"
    assert "destino" in (error.value.campos or {})


def test_origen_y_destino_deben_ser_distintos(db: Session) -> None:
    """RF-13: el destino debe ser distinto del origen."""
    with pytest.raises(DatosInvalidos) as error:
        service.validar_vuelo(db, datos_vuelo(origen="BOG", destino="BOG"))

    assert error.value.codigo == "datos_invalidos"
    assert "destino" in (error.value.campos or {})


@pytest.mark.parametrize("codigo", ["ZZZ", "MEX"])
def test_ciudad_fuera_del_catalogo(db: Session, codigo: str) -> None:
    """RF-13: solo se aceptan ciudades del catálogo."""
    with pytest.raises(DatosInvalidos) as error:
        service.validar_vuelo(db, datos_vuelo(destino=codigo))

    assert error.value.codigo == "datos_invalidos"
    assert "destino" in (error.value.campos or {})


def test_rechaza_salida_en_el_pasado(db: Session) -> None:
    """HU-13: una salida en el pasado es rechazada (RF-13)."""
    with pytest.raises(DatosInvalidos) as error:
        service.validar_vuelo(
            db,
            datos_vuelo(origen="PEI", destino="BOG", fecha_salida=date(2020, 1, 1)),
        )

    assert error.value.codigo == "datos_invalidos"
    assert "fecha_salida" in (error.value.campos or {})


def test_duplicado_misma_ruta_y_hora_y_acepta_veinte_minutos_despues(db: Session) -> None:
    """HU-13 · RF-16: 06:00 duplicado se rechaza; 06:20 se acepta."""
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
    )
    datos = datos_vuelo(
        origen="PEI",
        destino="BOG",
        fecha_salida=date(2026, 12, 10),
        hora_salida=time(6, 0),
        duracion_minutos=50,
    )

    with pytest.raises(service.VueloDuplicado) as error:
        service.validar_vuelo(db, datos)

    assert error.value.codigo == "vuelo_duplicado"
    assert "hora_salida" in (error.value.campos or {})

    aceptado = service.validar_vuelo(db, datos.model_copy(update={"hora_salida": time(6, 20)}))
    assert aceptado.salida == datetime(2026, 12, 10, 11, 20, tzinfo=UTC)


def test_un_vuelo_cancelado_no_bloquea_la_misma_ruta_y_hora(db: Session) -> None:
    """RF-16: la unicidad aplica a los vuelos programados, no a los cancelados."""
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
        estado="cancelado",
    )

    calculado = service.validar_vuelo(
        db,
        datos_vuelo(
            origen="PEI",
            destino="BOG",
            fecha_salida=date(2026, 12, 10),
            hora_salida=time(6, 0),
            duracion_minutos=50,
        ),
    )

    assert calculado.salida == datetime(2026, 12, 10, 11, 0, tzinfo=UTC)


def test_excepto_id_permite_validar_una_edicion(db: Session) -> None:
    """HU-15: al editar, el propio vuelo no cuenta como duplicado."""
    existente = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
    )

    calculado = service.validar_vuelo(
        db,
        datos_vuelo(
            origen="PEI",
            destino="BOG",
            fecha_salida=date(2026, 12, 10),
            hora_salida=time(6, 0),
            duracion_minutos=50,
        ),
        excepto_id=existente.id,
    )

    assert calculado.salida == existente.salida


def test_llegada_en_madrid_con_horario_de_verano(db: Session) -> None:
    """HU-13 · RF-15: 10/07/2026 22:00 Bogotá + 10 h llega 15:00 a Madrid (UTC+2)."""
    calculado = service.validar_vuelo(
        db,
        datos_vuelo(
            origen="BOG",
            destino="MAD",
            fecha_salida=date(2026, 7, 10),
            hora_salida=time(22, 0),
            duracion_minutos=600,
        ),
        ahora=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert calculado.salida == datetime(2026, 7, 11, 3, 0, tzinfo=UTC)
    assert calculado.llegada == datetime(2026, 7, 11, 13, 0, tzinfo=UTC)
    local = calculado.llegada.astimezone(ZoneInfo("Europe/Madrid"))
    assert (local.date(), local.hour, local.minute) == (date(2026, 7, 11), 15, 0)


def test_llegada_en_madrid_en_horario_estandar(db: Session) -> None:
    """HU-13 · RF-15: 10/12/2026 22:00 Bogotá + 10 h llega 14:00 a Madrid (UTC+1)."""
    calculado = service.validar_vuelo(
        db,
        datos_vuelo(
            origen="BOG",
            destino="MAD",
            fecha_salida=date(2026, 12, 10),
            hora_salida=time(22, 0),
            duracion_minutos=600,
        ),
        ahora=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert calculado.salida == datetime(2026, 12, 11, 3, 0, tzinfo=UTC)
    assert calculado.llegada == datetime(2026, 12, 11, 13, 0, tzinfo=UTC)
    local = calculado.llegada.astimezone(ZoneInfo("Europe/Madrid"))
    assert (local.date(), local.hour, local.minute) == (date(2026, 12, 11), 14, 0)


def test_llegada_en_buenos_aires(db: Session) -> None:
    """RF-15: Bogotá → Buenos Aires, 08:00 + 6 h 30 min llega 16:30 local (UTC-3)."""
    calculado = service.validar_vuelo(
        db,
        datos_vuelo(
            origen="BOG",
            destino="EZE",
            fecha_salida=date(2026, 12, 10),
            hora_salida=time(8, 0),
            duracion_minutos=390,
        ),
        ahora=datetime(2026, 1, 1, tzinfo=UTC),
    )

    local = calculado.llegada.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))
    assert (local.date(), local.hour, local.minute) == (date(2026, 12, 10), 16, 30)


@pytest.mark.parametrize(
    ("origen", "destino", "primera", "economica", "total"),
    [
        ("PEI", "BOG", 25, 125, 150),
        ("PEI", "MAD", 50, 200, 250),
    ],
)
def test_capacidad_segun_el_tipo_de_vuelo(
    db: Session, origen: str, destino: str, primera: int, economica: int, total: int
) -> None:
    """HU-13 · RF-13: nacional 25 + 125; internacional 50 + 200."""
    calculado = service.validar_vuelo(db, datos_vuelo(origen=origen, destino=destino))

    assert calculado.capacidad_primera == primera
    assert calculado.capacidad_economica == economica
    assert calculado.capacidad_total == total


def test_la_vista_previa_no_guarda_nada(db: Session) -> None:
    """HU-13: la vista previa aplica las validaciones pero no inserta el vuelo."""
    antes = db.scalar(select(func.count(Vuelo.id)))

    service.previsualizar_vuelo(db, datos_vuelo())

    assert db.scalar(select(func.count(Vuelo.id))) == antes


def test_las_funciones_no_hacen_commit(db: Session) -> None:
    """RNF-17: el servicio usa la transacción de quien llama."""
    db.execute(select(Vuelo.id).limit(0))
    transaccion = db.get_transaction()

    service.listar_ciudades(db)
    service.validar_vuelo(db, datos_vuelo())

    assert db.get_transaction() is transaccion


def test_la_secuencia_genera_codigos_unicos(db: Session) -> None:
    """SUP-01: el código STA-nnnnn sale de la secuencia y no se repite."""
    primero = crear_vuelo(db, origen="PEI", destino="BOG")
    segundo = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 12, 10, 12, 0, tzinfo=UTC),
    )

    assert re.fullmatch(r"STA-\d{5}", primero.codigo)
    assert re.fullmatch(r"STA-\d{5}", segundo.codigo)
    assert primero.codigo != segundo.codigo


def test_programar_vuelo_no_hace_commit(db: Session, crear_usuario) -> None:
    """HU-13 · RNF-17: guardar usa la transacción de quien llama; el commit es del router."""
    usuario = crear_usuario(Rol.ADMIN)
    db.execute(select(Vuelo.id).limit(0))
    transaccion = db.get_transaction()

    programado = service.programar_vuelo(
        db,
        datos_vuelo(origen="PEI", destino="MIA", duracion_minutos=240),
        usuario_id=usuario.id,
    )

    assert programado.vuelo.id is not None
    assert re.fullmatch(r"STA-\d{5}", programado.vuelo.codigo)
    assert programado.vuelo.tipo == "internacional"
    assert programado.ocupacion.tiquetes_vendidos == 0
    assert db.get_transaction() is transaccion
