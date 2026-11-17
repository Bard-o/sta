"""Búsqueda pública de vuelos (HU-20, HU-21, RF-27, RF-28, RNF-01, SUP-20)."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos, NoEncontrado
from app.modules.reservas.service import OcupacionVuelo
from app.modules.reservas.tests.fabricas import crear_compra, crear_reserva
from app.modules.vuelos import service
from app.modules.vuelos.tests.fabricas import (
    crear_promocion_bd,
    crear_vuelo,
    simular_ocupacion,
)

# Un instante fijo muy anterior a los vuelos de los tests: todos están a la venta.
AHORA = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
BOGOTA = "America/Bogota"
NUEVA_YORK = "America/New_York"


def _salida(fecha: date, hora: time, zona: str = BOGOTA) -> datetime:
    """La salida en UTC a partir de su fecha y hora locales (RF-15)."""
    return service.salida_en_utc(fecha, hora, zona)


# ---------- HU-20: filtros de la búsqueda ----------


def test_hu20_origen_y_precio_vigente_se_combinan(db: Session) -> None:
    """HU-20 · «Vuelos desde Pereira con precio entre $ 200.000 y $ 400.000» devuelve solo
    vuelos que cumplen ambas condiciones; el precio que se filtra es el vigente."""
    pereira = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
        precio_economica=280_000,
    )
    crear_promocion_bd(
        db,
        pereira,
        porcentaje=20,
        clases=["economica"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(days=30),
    )
    # Mismo rango de precio, pero sale de otra ciudad.
    crear_vuelo(
        db,
        origen="BOG",
        destino="MDE",
        salida=datetime(2026, 12, 10, 12, 0, tzinfo=UTC),
        precio_economica=210_000,
    )
    # Sale de Pereira, pero el precio vigente supera el máximo.
    crear_vuelo(
        db,
        origen="PEI",
        destino="MDE",
        salida=datetime(2026, 12, 10, 13, 0, tzinfo=UTC),
        precio_economica=500_000,
        precio_primera=900_000,
    )

    pagina = service.buscar_vuelos(
        db,
        service.FiltrosBusqueda(origen="PEI", precio_min=200_000, precio_max=240_000),
        ahora=AHORA,
    )

    assert pagina.total == 1
    assert [item.vuelo.id for item in pagina.items] == [pereira.id]
    assert pagina.items[0].economica.precio_base == 280_000
    assert pagina.items[0].economica.precio == 224_000


def test_rf27_el_rango_de_fechas_usa_la_hora_local_del_origen(db: Session) -> None:
    """RF-27 · «Vuelos a Nueva York entre el 17/10/2026 y el 18/10/2026» devuelve solo los
    que salen esos días, según la fecha local del origen."""
    vuelo_17 = crear_vuelo(
        db,
        origen="PEI",
        destino="JFK",
        tipo="internacional",
        salida=_salida(date(2026, 10, 17), time(23, 30)),
        duracion_minutos=300,
    )
    # Sale el 18/10/2026 a la 01:00 en Pereira: en UTC ya es el mismo 18, pero la fecha local
    # del origen es la que manda.
    vuelo_18 = crear_vuelo(
        db,
        origen="PEI",
        destino="JFK",
        tipo="internacional",
        salida=_salida(date(2026, 10, 18), time(1, 0)),
        duracion_minutos=300,
    )

    dia_17 = service.buscar_vuelos(
        db,
        service.FiltrosBusqueda(
            destino="JFK", fecha_desde=date(2026, 10, 17), fecha_hasta=date(2026, 10, 17)
        ),
        ahora=AHORA,
    )
    dia_18 = service.buscar_vuelos(
        db,
        service.FiltrosBusqueda(
            destino="JFK", fecha_desde=date(2026, 10, 18), fecha_hasta=date(2026, 10, 18)
        ),
        ahora=AHORA,
    )

    assert [item.vuelo.id for item in dia_17.items] == [vuelo_17.id]
    assert [item.vuelo.id for item in dia_18.items] == [vuelo_18.id]


def test_hu20_realizados_cancelados_salidos_y_cerrados_no_aparecen(db: Session) -> None:
    """HU-20 · los vuelos realizados, cancelados o que ya salieron no aparecen; tampoco los
    que ya pasaron su límite de venta (SUP-07)."""
    vendible = crear_vuelo(
        db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC), origen="PEI", destino="BOG"
    )
    crear_vuelo(
        db,
        salida=datetime(2026, 12, 10, 12, 0, tzinfo=UTC),
        estado="realizado",
        origen="PEI",
        destino="MDE",
    )
    crear_vuelo(
        db,
        salida=datetime(2026, 12, 10, 13, 0, tzinfo=UTC),
        estado="cancelado",
        origen="PEI",
        destino="CTG",
    )
    # Nacional que sale en 30 minutos: su límite de venta ya pasó.
    crear_vuelo(db, salida=AHORA + timedelta(minutes=30), origen="PEI", destino="BAQ")
    # Nacional que ya salió: tampoco está a la venta.
    crear_vuelo(db, salida=AHORA - timedelta(minutes=30), origen="PEI", destino="CLO")

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(), ahora=AHORA)

    assert pagina.total == 1
    assert [item.vuelo.id for item in pagina.items] == [vendible.id]


def test_hu20_los_filtros_se_combinan_todos(db: Session) -> None:
    """HU-20 · los filtros se combinan: un vuelo aparece solo si cumple todos."""
    dia = datetime(2026, 12, 10, 10, 0, tzinfo=UTC)
    candidato = crear_vuelo(
        db,
        origen="PEI",
        destino="MDE",
        tipo="nacional",
        salida=dia,
        duracion_minutos=50,
        precio_economica=280_000,
        precio_primera=750_000,
    )
    # Falla solo el destino.
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        tipo="nacional",
        salida=dia,
        duracion_minutos=50,
        precio_economica=280_000,
    )
    # Falla solo el tipo.
    crear_vuelo(
        db,
        origen="PEI",
        destino="MDE",
        tipo="internacional",
        salida=dia + timedelta(minutes=15),
        duracion_minutos=50,
        precio_economica=280_000,
    )
    # Falla solo la duración.
    crear_vuelo(
        db,
        origen="PEI",
        destino="MDE",
        tipo="nacional",
        salida=dia + timedelta(minutes=30),
        duracion_minutos=90,
        precio_economica=280_000,
    )
    # Falla solo el precio.
    crear_vuelo(
        db,
        origen="PEI",
        destino="MDE",
        tipo="nacional",
        salida=dia + timedelta(minutes=45),
        duracion_minutos=50,
        precio_economica=400_000,
    )
    # Falla solo la fecha.
    crear_vuelo(
        db,
        origen="PEI",
        destino="MDE",
        tipo="nacional",
        salida=dia + timedelta(days=1),
        duracion_minutos=50,
        precio_economica=280_000,
    )

    pagina = service.buscar_vuelos(
        db,
        service.FiltrosBusqueda(
            origen="PEI",
            destino="MDE",
            tipo="nacional",
            fecha_desde=date(2026, 12, 10),
            fecha_hasta=date(2026, 12, 10),
            duracion_min=40,
            duracion_max=60,
            precio_min=200_000,
            precio_max=300_000,
            clase="economica",
        ),
        ahora=AHORA,
    )

    assert pagina.total == 1
    assert [item.vuelo.id for item in pagina.items] == [candidato.id]


@pytest.mark.parametrize(
    ("orden", "esperado"),
    [
        ("precio", ["barato", "medio_1", "medio_2", "caro"]),
        ("fecha", ["medio_1", "caro", "medio_2", "barato"]),
        ("duracion", ["medio_2", "medio_1", "caro", "barato"]),
    ],
)
def test_sup20_ordena_por_precio_fecha_o_duracion(
    db: Session, orden: str, esperado: list[str]
) -> None:
    """SUP-20 · orden ascendente por precio (por defecto), fecha o duración, con desempate
    por salida y luego por id."""
    vuelos = {
        "caro": crear_vuelo(
            db,
            origen="PEI",
            destino="BOG",
            salida=_salida(date(2026, 12, 10), time(10, 0)),
            duracion_minutos=50,
            precio_economica=300_000,
        ),
        "barato": crear_vuelo(
            db,
            origen="PEI",
            destino="BOG",
            salida=_salida(date(2026, 12, 12), time(10, 0)),
            duracion_minutos=120,
            precio_economica=200_000,
        ),
        "medio_2": crear_vuelo(
            db,
            origen="PEI",
            destino="BOG",
            salida=_salida(date(2026, 12, 11), time(10, 0)),
            duracion_minutos=30,
            precio_economica=250_000,
        ),
        "medio_1": crear_vuelo(
            db,
            origen="PEI",
            destino="BOG",
            salida=_salida(date(2026, 12, 9), time(10, 0)),
            duracion_minutos=50,
            precio_economica=250_000,
        ),
    }

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(), orden=orden, ahora=AHORA)

    assert [item.vuelo.id for item in pagina.items] == [vuelos[nombre].id for nombre in esperado]


def test_sup20_veinte_resultados_por_pagina(db: Session) -> None:
    """SUP-20 · se paginan de 20 en 20 por defecto; el total no cambia entre páginas."""
    for dia in range(1, 26):
        crear_vuelo(
            db,
            origen="PEI",
            destino="BOG",
            salida=datetime(2026, 12, dia, 10, 0, tzinfo=UTC),
            precio_economica=280_000,
        )

    primera = service.buscar_vuelos(db, service.FiltrosBusqueda(), ahora=AHORA)
    segunda = service.buscar_vuelos(db, service.FiltrosBusqueda(), pagina=2, ahora=AHORA)

    assert primera.total == 25
    assert primera.pagina == 1
    assert primera.por_pagina == 20
    assert len(primera.items) == 20
    assert segunda.total == 25
    assert len(segunda.items) == 5
    assert {item.vuelo.id for item in primera.items}.isdisjoint(
        item.vuelo.id for item in segunda.items
    )


def test_sup20_una_clase_sin_cupo_se_marca_agotada(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SUP-20 · una clase sin cupo se marca agotada y el vuelo sigue en los resultados."""
    vuelo = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    simular_ocupacion(monkeypatch, {vuelo.id: OcupacionVuelo(vendidas_economica=125)})

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(), ahora=AHORA)

    assert pagina.total == 1
    detalle = pagina.items[0]
    assert detalle.economica.disponibles == 0
    assert detalle.economica.agotada is True
    assert detalle.primera.agotada is False


def test_sup20_un_vuelo_sin_cupo_en_ninguna_clase_sigue_en_los_resultados(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SUP-20 · un vuelo sin cupo en ninguna clase aparece marcado como agotado (ambas
    clases agotadas), no se descarta de la búsqueda."""
    vuelo = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    simular_ocupacion(
        monkeypatch,
        {vuelo.id: OcupacionVuelo(vendidas_economica=125, vendidas_primera=25)},
    )

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(), ahora=AHORA)

    assert pagina.total == 1
    detalle = pagina.items[0]
    assert detalle.economica.agotada is True
    assert detalle.primera.agotada is True


# ---------- HU-21: ida y regreso ----------


def _ida_pereira_nueva_york(db: Session) -> Any:
    """Ida que llega el 10/12/2026 a las 16:30 en Nueva York (21:30 UTC)."""
    return crear_vuelo(
        db,
        origen="PEI",
        destino="JFK",
        tipo="internacional",
        salida=datetime(2026, 12, 10, 14, 0, tzinfo=UTC),
        duracion_minutos=450,
    )


def test_hu21_ningun_regreso_sale_antes_de_la_llegada_de_la_ida(db: Session) -> None:
    """HU-21 · si la ida llega el 10/12 a las 16:30, no se ofrece ningún regreso que salga
    antes de esa hora; el que sale justo a esa hora tampoco (RF-28)."""
    ida = _ida_pereira_nueva_york(db)
    antes = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=_salida(date(2026, 12, 10), time(15, 0), NUEVA_YORK),
        duracion_minutos=300,
    )
    a_la_hora = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=_salida(date(2026, 12, 10), time(16, 30), NUEVA_YORK),
        duracion_minutos=300,
    )
    despues = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=_salida(date(2026, 12, 10), time(17, 0), NUEVA_YORK),
        duracion_minutos=300,
    )
    otro_dia = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=_salida(date(2026, 12, 11), time(10, 0), NUEVA_YORK),
        duracion_minutos=300,
    )

    pagina = service.regresos_de(db, ida.id, "CTG", date(2026, 12, 10), ahora=AHORA)

    ids = {item.vuelo.id for item in pagina.items}
    assert antes.id not in ids
    assert a_la_hora.id not in ids
    assert otro_dia.id not in ids
    assert [item.vuelo.id for item in pagina.items] == [despues.id]


def test_hu21_se_puede_armar_pereira_nueva_york_cartagena(db: Session) -> None:
    """HU-21 · se puede armar el trayecto Pereira → Nueva York → Cartagena: el regreso sale
    del destino de la ida hacia otra ciudad."""
    ida = _ida_pereira_nueva_york(db)
    regreso = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=_salida(date(2026, 12, 12), time(10, 0), NUEVA_YORK),
        duracion_minutos=300,
    )

    pagina = service.regresos_de(db, ida.id, "CTG", date(2026, 12, 12), ahora=AHORA)

    assert pagina.total == 1
    detalle = pagina.items[0]
    assert detalle.vuelo.id == regreso.id
    assert detalle.origen.codigo == "JFK"
    assert detalle.destino.codigo == "CTG"


def test_hu21_una_fecha_de_regreso_anterior_a_la_ida_se_rechaza(db: Session) -> None:
    """HU-21 · una fecha de regreso anterior a la de ida es rechazada (rango_invalido)."""
    ida = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=_salida(date(2026, 12, 10), time(10, 0)),
    )

    with pytest.raises(DatosInvalidos) as error:
        service.regresos_de(db, ida.id, "BOG", date(2026, 12, 9), ahora=AHORA)

    assert error.value.codigo == "rango_invalido"
    assert (error.value.campos or {})["fecha"] == (
        "La fecha de regreso no puede ser anterior a la de ida."
    )


def test_hu21_la_misma_fecha_local_de_la_ida_es_valida(db: Session) -> None:
    """HU-21 · solo es anterior si la fecha es anterior a la salida local de la ida; el mismo
    día se permite aunque en UTC la ida salga al día siguiente."""
    ida = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=_salida(date(2026, 12, 10), time(23, 0)),
    )

    pagina = service.regresos_de(db, ida.id, "BOG", date(2026, 12, 10), ahora=AHORA)

    assert pagina.total == 0
    assert pagina.items == []


@pytest.mark.parametrize("caso", ["inexistente", "cancelada", "realizada", "cerrada"])
def test_hu21_una_ida_que_no_esta_a_la_venta_no_tiene_regresos(db: Session, caso: str) -> None:
    """HU-21 · si la ida no existe o ya no está a la venta, se responde no_encontrado."""
    if caso == "inexistente":
        vuelo_ida_id = 999_999
    else:
        estado = "programado"
        salida = datetime(2026, 12, 10, 11, 0, tzinfo=UTC)
        if caso == "cancelada":
            estado = "cancelado"
        elif caso == "realizada":
            estado = "realizado"
        elif caso == "cerrada":
            salida = AHORA + timedelta(minutes=30)
        ida = crear_vuelo(db, estado=estado, salida=salida)
        vuelo_ida_id = ida.id

    with pytest.raises(NoEncontrado) as error:
        service.regresos_de(db, vuelo_ida_id, "BOG", date(2026, 12, 10), ahora=AHORA)

    assert error.value.mensaje == "El vuelo de ida no existe o ya no está a la venta."


# ---------- RNF-01 y casos del contrato ----------


def _contar_consultas(db: Session, al_buscar: Callable[[int], None]) -> list[str]:
    """Sentencias SQL emitidas al buscar una página de `por_pagina` resultados."""
    consultas: list[str] = []
    conexion = db.get_bind()

    def _contar(
        _conn: object,
        _cursor: object,
        sentencia: str,
        _parametros: object,
        _contexto: object,
        _muchas: bool,
    ) -> None:
        consultas.append(sentencia)

    event.listen(conexion, "before_cursor_execute", _contar)
    try:
        al_buscar(len(consultas))
    finally:
        event.remove(conexion, "before_cursor_execute", _contar)
    return consultas


def test_rnf01_el_numero_de_consultas_no_depende_del_tamano_de_la_pagina(
    db: Session,
) -> None:
    """RNF-01 · el precio y la ocupación de una página salen en un número fijo de consultas,
    no en una por vuelo."""
    for dia in range(1, 13):
        crear_vuelo(
            db,
            origen="PEI",
            destino="BOG",
            salida=datetime(2026, 12, dia, 10, 0, tzinfo=UTC),
        )

    def una_consulta(_inicio: int) -> None:
        service.buscar_vuelos(db, service.FiltrosBusqueda(), por_pagina=1, ahora=AHORA)

    def doce_consultas(_inicio: int) -> None:
        service.buscar_vuelos(db, service.FiltrosBusqueda(), por_pagina=12, ahora=AHORA)

    de_una = _contar_consultas(db, una_consulta)
    de_doce = _contar_consultas(db, doce_consultas)

    assert len(de_una) == len(de_doce)
    assert len(de_una) <= 5


def test_sin_filtros_devuelve_todo_lo_vendible_ordenado_por_precio(db: Session) -> None:
    """HU-20 · sin filtros se devuelven todos los vuelos a la venta, del más barato al más caro."""
    caro = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC), origen="PEI")
    barato = crear_vuelo(
        db,
        origen="MDE",
        destino="CTG",
        salida=datetime(2026, 12, 10, 12, 0, tzinfo=UTC),
        precio_economica=150_000,
    )

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(), ahora=AHORA)

    assert [item.vuelo.id for item in pagina.items] == [barato.id, caro.id]


def test_sin_clase_el_precio_es_el_menor_de_las_dos(db: Session) -> None:
    """RF-27 · sin `clase`, el filtro de precio usa el menor precio vigente de las dos clases."""
    vuelo = crear_vuelo(
        db,
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
        precio_economica=500_000,
        precio_primera=750_000,
    )
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=50,
        clases=["primera"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(days=30),
    )

    sin_clase = service.buscar_vuelos(
        db, service.FiltrosBusqueda(precio_min=300_000, precio_max=400_000), ahora=AHORA
    )
    en_economica = service.buscar_vuelos(
        db,
        service.FiltrosBusqueda(precio_min=300_000, precio_max=400_000, clase="economica"),
        ahora=AHORA,
    )

    assert [item.vuelo.id for item in sin_clase.items] == [vuelo.id]
    assert sin_clase.items[0].primera.precio == 375_000
    assert en_economica.total == 0


def test_el_rango_de_horas_usa_la_hora_local_del_origen(db: Session) -> None:
    """RF-27 · el rango de horas se compara con la salida en la hora local del origen."""
    noche = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=_salida(date(2026, 12, 10), time(23, 30)),
    )
    crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        salida=_salida(date(2026, 12, 10), time(10, 0)),
    )

    pagina = service.buscar_vuelos(
        db,
        service.FiltrosBusqueda(
            origen="PEI",
            fecha_desde=date(2026, 12, 10),
            fecha_hasta=date(2026, 12, 10),
            hora_desde=time(22, 0),
            hora_hasta=time(23, 59),
        ),
        ahora=AHORA,
    )

    assert [item.vuelo.id for item in pagina.items] == [noche.id]


def test_codigo_parcial_no_distingue_mayusculas(db: Session) -> None:
    """RF-27 · el código filtra por una parte, sin distinguir mayúsculas."""
    primero = crear_vuelo(
        db,
        codigo="STA-00030",
        salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
        origen="PEI",
        destino="BOG",
    )
    segundo = crear_vuelo(
        db,
        codigo="STA-00031",
        salida=datetime(2026, 12, 10, 12, 0, tzinfo=UTC),
        origen="PEI",
        destino="MDE",
    )
    crear_vuelo(
        db,
        codigo="STA-00040",
        salida=datetime(2026, 12, 10, 13, 0, tzinfo=UTC),
        origen="PEI",
        destino="CTG",
    )

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(codigo="sta-0003"), ahora=AHORA)

    assert {item.vuelo.id for item in pagina.items} == {primero.id, segundo.id}


def test_una_ciudad_que_no_esta_en_el_catalogo_no_es_un_error(db: Session) -> None:
    """RF-27 · un código de ciudad desconocido no es un error: no hay vuelos que lo cumplan."""
    crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC), origen="PEI")

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(origen="ZZZ"), ahora=AHORA)

    assert pagina.total == 0
    assert pagina.items == []


def test_la_disponibilidad_descuenta_reservas_y_bloqueos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-20 · `disponibles` descuenta las sillas vendidas, reservadas y bloqueadas."""
    vuelo = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    cliente = crear_usuario()

    crear_reserva(db, cliente.id, vuelo, clase="economica", cantidad=2)
    crear_compra(db, cliente.id, vuelo, clase="economica", cantidad=3)
    crear_compra(
        db,
        cliente.id,
        vuelo,
        clase="economica",
        cantidad=1,
        estado="pendiente",
        estado_tiquete="bloqueado",
        bloqueo_hasta=AHORA + timedelta(minutes=15),
    )
    crear_reserva(db, cliente.id, vuelo, clase="primera", cantidad=1)

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(), ahora=AHORA)

    detalle = pagina.items[0]
    assert detalle.economica.disponibles == 125 - 2 - 3 - 1
    assert detalle.primera.disponibles == 25 - 1


def test_una_promocion_vencida_o_programada_no_cambia_el_precio(db: Session) -> None:
    """RF-24 · solo la promoción vigente descuenta; la vencida y la futura no se aplican."""
    vuelo = crear_vuelo(
        db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC), precio_economica=280_000
    )
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=50,
        clases=["economica"],
        inicio=AHORA - timedelta(days=2),
        fin=AHORA - timedelta(days=1),
    )
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=50,
        clases=["primera"],
        inicio=AHORA + timedelta(days=1),
        fin=AHORA + timedelta(days=2),
    )

    pagina = service.buscar_vuelos(db, service.FiltrosBusqueda(), ahora=AHORA)

    detalle = pagina.items[0]
    assert detalle.economica.precio == 280_000
    assert detalle.economica.promocion is None
    assert detalle.primera.precio == 750_000
    assert detalle.primera.promocion is None
