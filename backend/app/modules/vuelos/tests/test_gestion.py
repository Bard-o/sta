"""Listado de gestión y edición de vuelos (HU-15, RF-18, RF-26)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos, NoEncontrado
from app.core.security import Rol
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.noticias.models import Noticia
from app.modules.reservas import service as reservas_service
from app.modules.reservas.service import OcupacionVuelo
from app.modules.vuelos import service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.schemas import VueloEntrada
from app.modules.vuelos.tests.fabricas import crear_vuelo, simular_ocupacion

# Un instante fijo antes de todos los vuelos de los tests (mañana del 20 de octubre de 2026).
AHORA = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


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


# ---------- Listado del administrador (HU-15) ----------


def test_listado_por_defecto_solo_programados_y_por_salida_ascendente(db: Session) -> None:
    """HU-15: sin filtros, el listado trae los programados de la salida más próxima a la más
    lejana e ignora los realizados y cancelados."""
    tarde = crear_vuelo(db, salida=datetime(2026, 12, 10, 15, 0, tzinfo=UTC))
    temprano = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    crear_vuelo(db, estado="cancelado", salida=datetime(2026, 12, 9, 11, 0, tzinfo=UTC))
    crear_vuelo(db, estado="realizado", salida=datetime(2026, 12, 8, 11, 0, tzinfo=UTC))

    pagina = service.listar_vuelos_gestion(db, ahora=AHORA)

    assert [item.vuelo.id for item in pagina.items] == [temprano.id, tarde.id]
    assert pagina.total == 2
    assert pagina.pagina == 1
    assert pagina.por_pagina == 20


@pytest.mark.parametrize("estado", ["realizado", "cancelado"])
def test_listado_de_realizados_y_cancelados_va_del_mas_reciente_al_mas_antiguo(
    db: Session, estado: str
) -> None:
    """HU-15: los realizados y los cancelados van del más reciente al más antiguo."""
    viejo = crear_vuelo(
        db, estado=estado, salida=datetime(2026, 12, 8, 11, 0, tzinfo=UTC), duracion_minutos=60
    )
    nuevo = crear_vuelo(
        db, estado=estado, salida=datetime(2026, 12, 9, 11, 0, tzinfo=UTC), duracion_minutos=60
    )

    pagina = service.listar_vuelos_gestion(db, estado=estado, ahora=AHORA)

    assert [item.vuelo.id for item in pagina.items] == [nuevo.id, viejo.id]


def test_listado_filtra_por_fechas_de_colombia_inclusivas(db: Session) -> None:
    """HU-15: `desde` y `hasta` son fechas de Colombia, inclusivas, sobre la salida."""
    temprano = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    # 23:59 del 10 de diciembre en Bogotá.
    ultimo = crear_vuelo(db, salida=datetime(2026, 12, 11, 4, 59, tzinfo=UTC), destino="MDE")
    # 00:00 del 11 de diciembre en Bogotá: queda por fuera.
    crear_vuelo(db, salida=datetime(2026, 12, 11, 5, 0, tzinfo=UTC), destino="CLO")

    pagina = service.listar_vuelos_gestion(
        db, desde=date(2026, 12, 10), hasta=date(2026, 12, 10), ahora=AHORA
    )

    assert [item.vuelo.id for item in pagina.items] == [temprano.id, ultimo.id]


def test_listado_de_realizados_filtra_por_la_llegada(db: Session) -> None:
    """HU-15: en los realizados, las fechas se aplican a la llegada y no a la salida."""
    # Sale el 9 a las 22:00 de Colombia y llega el 10 a las 00:00 de Colombia.
    cruza_la_medianoche = crear_vuelo(
        db,
        estado="realizado",
        salida=datetime(2026, 12, 10, 3, 0, tzinfo=UTC),
        duracion_minutos=120,
    )
    crear_vuelo(
        db,
        estado="realizado",
        salida=datetime(2026, 12, 11, 3, 0, tzinfo=UTC),
        duracion_minutos=120,
        destino="MDE",
    )

    pagina = service.listar_vuelos_gestion(
        db,
        estado="realizado",
        desde=date(2026, 12, 10),
        hasta=date(2026, 12, 10),
        ahora=AHORA,
    )

    assert [item.vuelo.id for item in pagina.items] == [cruza_la_medianoche.id]


def test_listado_busca_por_codigo_y_por_ciudad_sin_tildes(db: Session) -> None:
    """HU-15: `q` busca el código o el nombre de la ciudad, sin distinguir tildes."""
    vuelo = crear_vuelo(db, origen="PEI", destino="BOG")

    assert [
        item.vuelo.id for item in service.listar_vuelos_gestion(db, q="bogota", ahora=AHORA).items
    ] == [vuelo.id]
    assert [
        item.vuelo.id for item in service.listar_vuelos_gestion(db, q="Pereira", ahora=AHORA).items
    ] == [vuelo.id]
    assert [
        item.vuelo.id
        for item in service.listar_vuelos_gestion(db, q=vuelo.codigo.lower(), ahora=AHORA).items
    ] == [vuelo.id]
    assert service.listar_vuelos_gestion(db, q="no-existe", ahora=AHORA).items == []


def test_listado_pagina_y_devuelve_el_total_filtrado(db: Session) -> None:
    """HU-15: `pagina` y `por_pagina` recortan la página; `total` cuenta todo el filtro."""
    for hora in (11, 12, 13):
        crear_vuelo(db, salida=datetime(2026, 12, 10, hora, 0, tzinfo=UTC))

    primera = service.listar_vuelos_gestion(db, pagina=1, por_pagina=2, ahora=AHORA)
    segunda = service.listar_vuelos_gestion(db, pagina=2, por_pagina=2, ahora=AHORA)

    assert primera.total == 3
    assert len(primera.items) == 2
    assert len(segunda.items) == 1
    assert (segunda.pagina, segunda.por_pagina) == (2, 2)


def test_listado_trae_la_ocupacion_de_la_pagina_en_una_sola_llamada(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-15: la ocupación de toda la página se pide una sola vez a reservas."""
    primero = crear_vuelo(db, salida=datetime(2026, 12, 10, 11, 0, tzinfo=UTC))
    segundo = crear_vuelo(db, salida=datetime(2026, 12, 10, 12, 0, tzinfo=UTC))
    llamadas: list[list[int]] = []

    def _ocupacion(_db: Session, vuelo_ids: list[int]) -> dict[int, OcupacionVuelo]:
        llamadas.append(list(vuelo_ids))
        return {vuelo_id: OcupacionVuelo(vendidas_economica=2) for vuelo_id in vuelo_ids}

    monkeypatch.setattr(reservas_service, "ocupacion_de_vuelos", _ocupacion)

    pagina = service.listar_vuelos_gestion(db, ahora=AHORA)

    assert len(llamadas) == 1
    assert sorted(llamadas[0]) == sorted([primero.id, segundo.id])
    assert pagina.items[0].ocupacion.tiquetes_vendidos == 2


# ---------- Detalle de gestión (HU-15) ----------


def test_gestion_de_un_vuelo_inexistente(db: Session) -> None:
    """HU-15: un vuelo que no existe responde `no_encontrado`."""
    with pytest.raises(NoEncontrado) as error:
        service.obtener_vuelo_gestion(db, 999_999, ahora=AHORA)

    assert error.value.codigo == "no_encontrado"


@pytest.mark.parametrize(
    ("ocupacion", "cancelable"),
    [
        (OcupacionVuelo(reservas_activas=1, reservadas_economica=1), True),
        (OcupacionVuelo(vendidas_economica=1), False),
    ],
)
def test_gestion_bloquea_con_reservas_y_con_compras(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    ocupacion: OcupacionVuelo,
    cancelable: bool,
) -> None:
    """HU-15 · RF-18: con una reserva activa o una compra no se edita y se indica el motivo."""
    vuelo = crear_vuelo(db)
    simular_ocupacion(monkeypatch, {vuelo.id: ocupacion})

    gestion = service.obtener_vuelo_gestion(db, vuelo.id, ahora=AHORA)

    assert gestion.editable is False
    assert gestion.motivo_no_editable == "El vuelo tiene reservas activas o compras."
    assert gestion.cancelable is cancelable


def test_vuelo_vuelve_a_ser_editable_cuando_la_reserva_ya_no_esta(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-15 · RF-18: si la única reserva vence o se cancela, el vuelo vuelve a ser editable."""
    vuelo = crear_vuelo(db)
    simular_ocupacion(monkeypatch, {vuelo.id: OcupacionVuelo(reservas_activas=1)})
    assert service.obtener_vuelo_gestion(db, vuelo.id, ahora=AHORA).editable is False

    simular_ocupacion(monkeypatch)

    assert service.obtener_vuelo_gestion(db, vuelo.id, ahora=AHORA).editable is True


@pytest.mark.parametrize(
    ("estado", "salida", "motivo"),
    [
        (
            "realizado",
            datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
            "El vuelo ya se realizó o está cancelado.",
        ),
        (
            "cancelado",
            datetime(2026, 12, 10, 11, 0, tzinfo=UTC),
            "El vuelo ya se realizó o está cancelado.",
        ),
        (
            "programado",
            datetime(2026, 10, 19, 11, 0, tzinfo=UTC),
            "El vuelo ya salió.",
        ),
    ],
)
def test_gestion_marca_sin_edicion_un_vuelo_cerrado(
    db: Session, estado: str, salida: datetime, motivo: str
) -> None:
    """HU-15 · RF-18: un vuelo realizado, cancelado o que ya salió no se puede editar."""
    vuelo = crear_vuelo(db, estado=estado, salida=salida)

    gestion = service.obtener_vuelo_gestion(db, vuelo.id, ahora=AHORA)

    assert gestion.editable is False
    assert gestion.motivo_no_editable == motivo
    assert gestion.cancelable is False


# ---------- Edición (HU-15, RF-18, RF-26) ----------


def test_editar_recalcula_tipo_capacidad_y_llegada_y_conserva_el_codigo(
    db: Session, crear_usuario
) -> None:
    """HU-15 · RF-18: editar recalcula tipo, capacidad y llegada; el código no cambia."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, origen="PEI", destino="BOG", duracion_minutos=50)
    codigo = vuelo.codigo

    gestion = service.editar_vuelo(
        db,
        vuelo.id,
        datos_vuelo(
            origen="PEI",
            destino="MAD",
            duracion_minutos=600,
            precio_economica=2_500_000,
            precio_primera=7_000_000,
        ),
        usuario_id=usuario.id,
        ahora=AHORA,
    )

    editado = gestion.vuelo
    assert editado.codigo == codigo
    assert editado.tipo == "internacional"
    assert (editado.capacidad_primera, editado.capacidad_economica) == (50, 200)
    assert editado.llegada == editado.salida + timedelta(minutes=600)
    assert editado.destino_codigo == "MAD"
    assert editado.precio_economica == 2_500_000


def test_editar_actualiza_sus_noticias(db: Session, crear_usuario) -> None:
    """HU-15: editar el vuelo actualiza los datos que muestra su noticia."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = service.programar_vuelo(
        db, datos_vuelo(origen="PEI", destino="BOG", duracion_minutos=50), usuario_id=usuario.id
    ).vuelo

    service.editar_vuelo(
        db,
        vuelo.id,
        datos_vuelo(origen="PEI", destino="MAD", duracion_minutos=600, precio_economica=2_500_000),
        usuario_id=usuario.id,
        ahora=AHORA,
    )

    noticia = db.scalars(select(Noticia).where(Noticia.vuelo_id == vuelo.id)).one()
    assert noticia.destino_codigo == "MAD"
    assert noticia.destino_nombre == "Madrid"
    assert noticia.precio_economica == 2_500_000
    assert noticia.salida == vuelo.salida
    assert noticia.imagen_url == "/imagenes/ciudades/MAD.jpg"


def test_editar_audita_solo_los_campos_que_cambiaron(db: Session, crear_usuario) -> None:
    """HU-15 · RF-26: editar el precio deja en la auditoría el precio anterior y el nuevo."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = service.programar_vuelo(db, datos_vuelo(), usuario_id=usuario.id).vuelo

    service.editar_vuelo(
        db,
        vuelo.id,
        datos_vuelo(precio_economica=2_500_000),
        usuario_id=usuario.id,
        ahora=AHORA,
    )

    registro = db.scalars(
        select(RegistroAuditoria).where(RegistroAuditoria.accion == "vuelo.editar")
    ).one()
    assert registro.entidad == "vuelo"
    assert registro.entidad_id == vuelo.id
    assert registro.usuario_id == usuario.id
    assert registro.antes == {"precio_economica": 2_450_000}
    assert registro.despues == {"precio_economica": 2_500_000}


def test_editar_sin_cambios_no_deja_registro_de_auditoria(db: Session, crear_usuario) -> None:
    """HU-15 · RF-26: un PUT idéntico responde bien y no ensucia la auditoría."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = service.programar_vuelo(db, datos_vuelo(), usuario_id=usuario.id).vuelo

    service.editar_vuelo(db, vuelo.id, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA)

    editados = db.scalar(
        select(func.count(RegistroAuditoria.id)).where(RegistroAuditoria.accion == "vuelo.editar")
    )
    assert editados == 0


def test_editar_con_reservas_falla_con_vuelo_con_reservas(
    db: Session, crear_usuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-15 · RF-18: con reservas activas, la edición falla con `vuelo_con_reservas`."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db)
    simular_ocupacion(monkeypatch, {vuelo.id: OcupacionVuelo(reservas_activas=1)})

    with pytest.raises(service.VueloConReservas) as error:
        service.editar_vuelo(db, vuelo.id, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA)

    assert error.value.codigo == "vuelo_con_reservas"


@pytest.mark.parametrize(
    ("estado", "salida"),
    [
        ("realizado", datetime(2026, 12, 10, 11, 0, tzinfo=UTC)),
        ("cancelado", datetime(2026, 12, 10, 11, 0, tzinfo=UTC)),
        ("programado", datetime(2026, 10, 19, 11, 0, tzinfo=UTC)),
    ],
)
def test_editar_un_vuelo_cerrado_falla_con_vuelo_cerrado(
    db: Session, crear_usuario, estado: str, salida: datetime
) -> None:
    """HU-15 · RF-18: un vuelo realizado, cancelado o que ya salió no se edita."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, estado=estado, salida=salida)

    with pytest.raises(service.VueloCerrado) as error:
        service.editar_vuelo(db, vuelo.id, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA)

    assert error.value.codigo == "vuelo_cerrado"


def test_editar_no_cuenta_el_propio_vuelo_como_duplicado(db: Session, crear_usuario) -> None:
    """HU-15 · RF-16: la unicidad de ruta y salida excluye al vuelo que se edita."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db)

    gestion = service.editar_vuelo(
        db,
        vuelo.id,
        datos_vuelo(
            origen="PEI",
            destino="BOG",
            fecha_salida=date(2026, 12, 10),
            hora_salida=time(6, 0),
            duracion_minutos=60,
        ),
        usuario_id=usuario.id,
        ahora=AHORA,
    )

    assert gestion.vuelo.duracion_minutos == 60


def test_editar_con_datos_invalidos_no_cambia_el_vuelo(db: Session, crear_usuario) -> None:
    """HU-15 · RF-18: las validaciones de HU-13 se aplican antes de tocar el vuelo."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db)
    precio_original = vuelo.precio_economica

    with pytest.raises(DatosInvalidos):
        service.editar_vuelo(
            db,
            vuelo.id,
            datos_vuelo(fecha_salida=date(2020, 1, 1), precio_economica=2_500_000),
            usuario_id=usuario.id,
            ahora=AHORA,
        )

    assert vuelo.precio_economica == precio_original


def test_editar_no_hace_commit(db: Session, crear_usuario) -> None:
    """HU-15 · RNF-17: editar usa la transacción de quien llama; el commit es del router."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db)
    db.execute(select(Vuelo.id).limit(0))
    transaccion = db.get_transaction()

    service.editar_vuelo(db, vuelo.id, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA)

    assert db.get_transaction() is transaccion
