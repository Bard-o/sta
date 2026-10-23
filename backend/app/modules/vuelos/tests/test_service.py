"""Validaciones y cálculos compartidos del módulo (HU-13, HU-14, RF-12 a RF-17)."""

import re
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos
from app.core.security import Rol
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.noticias.models import Noticia
from app.modules.vuelos import service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.schemas import SerieVuelosEntrada, VueloEntrada
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


# ---------- Series (HU-14) ----------

# 00:00 del 1 de octubre de 2026 en Bogotá.
PRIMER_DIA = datetime(2026, 10, 1, 5, 0, tzinfo=UTC)
# Todos los lunes de octubre a diciembre de 2026.
LUNES = [
    date(2026, 10, 5),
    date(2026, 10, 12),
    date(2026, 10, 19),
    date(2026, 10, 26),
    date(2026, 11, 2),
    date(2026, 11, 9),
    date(2026, 11, 16),
    date(2026, 11, 23),
    date(2026, 11, 30),
    date(2026, 12, 7),
    date(2026, 12, 14),
    date(2026, 12, 21),
    date(2026, 12, 28),
]
SALIDAS = [datetime.combine(fecha, time(11, 0), tzinfo=UTC) for fecha in LUNES]


def datos_serie(**cambios: object) -> SerieVuelosEntrada:
    base: dict[str, object] = {
        "origen": "PEI",
        "destino": "BOG",
        "hora_salida": time(6, 0),
        "duracion_minutos": 50,
        "precio_economica": 280_000,
        "precio_primera": 750_000,
        "dias_semana": ["lun"],
        "desde": date(2026, 10, 1),
        "hasta": date(2026, 12, 31),
    }
    base.update(cambios)
    return SerieVuelosEntrada(**base)


def test_serie_de_lunes_del_ejemplo_crea_un_vuelo_por_lunes(db: Session, crear_usuario) -> None:
    """HU-14 · RF-17: «todos los lunes a las 06:00, Pereira → Bogotá, de octubre a diciembre
    de 2026» crea un vuelo por cada lunes del periodo."""
    usuario = crear_usuario(Rol.ADMIN)

    serie = service.programar_serie(db, datos_serie(), usuario_id=usuario.id, ahora=PRIMER_DIA)

    assert [vuelo.salida for vuelo in serie.creados] == SALIDAS
    assert serie.omitidas == []
    assert len({vuelo.codigo for vuelo in serie.creados}) == len(LUNES)
    for vuelo in serie.creados:
        assert re.fullmatch(r"STA-\d{5}", vuelo.codigo)
        assert (vuelo.origen_codigo, vuelo.destino_codigo) == ("PEI", "BOG")
        assert vuelo.duracion_minutos == 50
        assert (vuelo.precio_economica, vuelo.precio_primera) == (280_000, 750_000)
        assert (vuelo.capacidad_primera, vuelo.capacidad_economica) == (25, 125)
        assert vuelo.estado == "programado"


def test_cada_ocurrencia_tiene_su_noticia_y_su_auditoria(db: Session, crear_usuario) -> None:
    """HU-14 · RF-17/RF-26: cada ocurrencia tiene su código, su noticia y su auditoría."""
    usuario = crear_usuario(Rol.ADMIN)

    serie = service.programar_serie(db, datos_serie(), usuario_id=usuario.id, ahora=PRIMER_DIA)

    noticias = {noticia.vuelo_id: noticia for noticia in db.scalars(select(Noticia))}
    registros = list(
        db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "vuelo.crear"))
    )
    assert set(noticias) == {vuelo.id for vuelo in serie.creados}
    assert {registro.entidad_id for registro in registros} == {vuelo.id for vuelo in serie.creados}
    for vuelo in serie.creados:
        assert noticias[vuelo.id].vuelo_codigo == vuelo.codigo
        assert noticias[vuelo.id].titulo == "Nuevo vuelo Pereira → Bogotá"
    for registro in registros:
        assert registro.usuario_id == usuario.id
        assert registro.entidad == "vuelo"
        assert registro.despues is not None
        assert registro.despues["estado"] == "programado"


def test_editar_o_cancelar_una_ocurrencia_no_afecta_a_las_demas(db: Session, crear_usuario) -> None:
    """HU-14 · RF-17: editar o cancelar una ocurrencia no afecta a las demás."""
    usuario = crear_usuario(Rol.ADMIN)
    serie = service.programar_serie(db, datos_serie(), usuario_id=usuario.id, ahora=PRIMER_DIA)

    primera = serie.creados[0]
    primera.estado = "cancelado"
    primera.precio_economica = 1
    db.flush()

    for vuelo in serie.creados[1:]:
        db.refresh(vuelo)
        assert vuelo.estado == "programado"
        assert vuelo.precio_economica == 280_000


def test_serie_omite_las_salidas_en_pasado(db: Session, crear_usuario) -> None:
    """HU-14 · RF-17: las fechas anteriores a hoy se omiten y se informan, no son un error."""
    usuario = crear_usuario(Rol.ADMIN)

    serie = service.programar_serie(
        db,
        datos_serie(),
        usuario_id=usuario.id,
        ahora=datetime(2026, 12, 1, 5, 0, tzinfo=UTC),
    )

    assert [omitida.fecha for omitida in serie.omitidas] == LUNES[:9]
    assert {omitida.codigo for omitida in serie.omitidas} == {"salida_en_pasado"}
    assert {omitida.motivo for omitida in serie.omitidas} == {"La salida ya pasó."}
    assert [vuelo.salida for vuelo in serie.creados] == SALIDAS[9:]


def test_serie_omite_los_vuelos_duplicados(db: Session, crear_usuario) -> None:
    """HU-14 · RF-16/RF-17: una fecha con un vuelo igual se omite y se informa."""
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 11, 9, 11, 0, tzinfo=UTC),
    )
    usuario = crear_usuario(Rol.ADMIN)

    serie = service.programar_serie(db, datos_serie(), usuario_id=usuario.id, ahora=PRIMER_DIA)

    assert len(serie.creados) == len(LUNES) - 1
    assert [omitida.fecha for omitida in serie.omitidas] == [date(2026, 11, 9)]
    assert serie.omitidas[0].codigo == "vuelo_duplicado"
    assert serie.omitidas[0].motivo == "Ya existe un vuelo igual."


def test_una_fecha_pasada_se_reporta_como_pasada_y_no_como_duplicada(
    db: Session, crear_usuario
) -> None:
    """HU-14 · RF-17: si la fecha ya pasó, el motivo es `salida_en_pasado` aunque haya choque."""
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 10, 5, 11, 0, tzinfo=UTC),
    )
    usuario = crear_usuario(Rol.ADMIN)

    serie = service.programar_serie(
        db,
        datos_serie(),
        usuario_id=usuario.id,
        ahora=datetime(2026, 12, 1, 5, 0, tzinfo=UTC),
    )

    primera = serie.omitidas[0]
    assert primera.fecha == date(2026, 10, 5)
    assert primera.codigo == "salida_en_pasado"


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        (
            {"desde": date(2027, 1, 10), "hasta": date(2027, 1, 1)},
            "La fecha final no puede ser anterior a la inicial.",
        ),
        (
            {"desde": date(2026, 1, 1), "hasta": date(2027, 10, 2)},
            "Máximo 12 meses desde hoy.",
        ),
    ],
)
def test_serie_rechaza_periodos_invalidos(
    db: Session, cambios: dict[str, object], mensaje: str
) -> None:
    """HU-14 · SUP-37: el periodo invertido o de más de 12 meses rechaza toda la serie."""
    with pytest.raises(DatosInvalidos) as error:
        service.previsualizar_serie(db, datos_serie(**cambios), ahora=PRIMER_DIA)

    assert error.value.codigo == "datos_invalidos"
    assert error.value.campos == {"hasta": mensaje}


def test_el_limite_de_doce_meses_es_inclusivo(db: Session) -> None:
    """HU-14 · SUP-37: una serie que termina justo 12 meses después de hoy se acepta."""
    serie = service.previsualizar_serie(
        db,
        datos_serie(desde=date(2027, 10, 1), hasta=date(2027, 10, 1)),
        ahora=PRIMER_DIA,
    )

    assert serie.tipo == "nacional"
    assert serie.fechas == []


def test_el_limite_de_doce_meses_maneja_el_29_de_febrero(db: Session) -> None:
    """HU-14 · SUP-37: desde un 29 de febrero, el límite es el 28 de febrero del año siguiente."""
    bisiesto = datetime(2028, 2, 29, 5, 0, tzinfo=UTC)

    aceptada = service.previsualizar_serie(
        db,
        datos_serie(desde=date(2028, 2, 28), hasta=date(2029, 2, 28)),
        ahora=bisiesto,
    )
    assert aceptada.tipo == "nacional"

    with pytest.raises(DatosInvalidos):
        service.previsualizar_serie(
            db,
            datos_serie(desde=date(2028, 2, 28), hasta=date(2029, 3, 1)),
            ahora=bisiesto,
        )


def test_dias_repetidos_no_duplican_las_fechas(db: Session) -> None:
    """HU-14 · RF-17: un día repetido en `dias_semana` no crea dos veces la misma fecha."""
    serie = service.previsualizar_serie(
        db, datos_serie(dias_semana=["lun", "lun"]), ahora=PRIMER_DIA
    )

    assert serie.fechas == LUNES


def test_la_vista_previa_de_la_serie_no_guarda_nada(db: Session) -> None:
    """HU-14: la vista previa de la serie no inserta vuelos, noticias ni auditorías."""
    vuelos_antes = db.scalar(select(func.count(Vuelo.id)))
    noticias_antes = db.scalar(select(func.count(Noticia.id)))
    auditorias_antes = db.scalar(select(func.count(RegistroAuditoria.id)))

    service.previsualizar_serie(db, datos_serie(), ahora=PRIMER_DIA)

    assert db.scalar(select(func.count(Vuelo.id))) == vuelos_antes
    assert db.scalar(select(func.count(Noticia.id))) == noticias_antes
    assert db.scalar(select(func.count(RegistroAuditoria.id))) == auditorias_antes


def test_la_serie_valida_la_ruta_y_el_catalogo(db: Session) -> None:
    """HU-14 · RF-14: una ruta prohibida o una ciudad fuera del catálogo rechazan la serie."""
    with pytest.raises(service.RutaNoPermitida):
        service.previsualizar_serie(db, datos_serie(origen="MZL", destino="MIA"), ahora=PRIMER_DIA)

    with pytest.raises(DatosInvalidos) as error:
        service.previsualizar_serie(db, datos_serie(destino="ZZZ"), ahora=PRIMER_DIA)

    assert "destino" in (error.value.campos or {})


def test_programar_serie_no_hace_commit(db: Session, crear_usuario) -> None:
    """HU-14 · RNF-17: la serie usa la transacción de quien llama; el commit es del router."""
    usuario = crear_usuario(Rol.ADMIN)
    db.execute(select(Vuelo.id).limit(0))
    transaccion = db.get_transaction()

    serie = service.programar_serie(
        db,
        datos_serie(desde=date(2026, 12, 7), hasta=date(2026, 12, 14)),
        usuario_id=usuario.id,
        ahora=PRIMER_DIA,
    )

    assert len(serie.creados) == 2
    assert db.get_transaction() is transaccion
