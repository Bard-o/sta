"""Mis viajes: reservas y compras del cliente con filtros y paginación (HU-27, RF-45).

Los tests llaman al service con `ahora=AHORA` (1 de diciembre de 2026, 10:00 UTC).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import CorreoEnCola
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas import service
from app.modules.reservas.models import Transaccion
from app.modules.reservas.schemas import PaginaViajes
from app.modules.reservas.tests.apoyo import (
    AHORA,
    SALIDA,
    cliente_verificado,
    entrada,
    viajero,
)
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import crear_vuelo

P = 280_000


def _vuelo(db: Session, horas: int = 0, **cambios: Any) -> Vuelo:
    """Vuelo que sale `horas` después de SALIDA: cada uno tiene su propia salida."""
    return crear_vuelo(db, salida=SALIDA + timedelta(hours=horas), **cambios)


def _reservar(
    db: Session,
    cliente_id: int,
    vuelo: Vuelo,
    documento: str,
    *,
    ahora: datetime = AHORA,
) -> Transaccion:
    datos = entrada([vuelo], [viajero(documento, email=f"{documento}@example.com")])
    return service.crear_reserva(db, cliente_id, datos, ahora=ahora)


def _saldo(db: Session, cliente_id: int, valor: int = 5_000_000) -> None:
    crear_movimiento(db, cliente_id, valor=valor, saldo_resultante=valor)


def _ids(pagina: PaginaViajes) -> list[int]:
    return [viaje.id for viaje in pagina.items]


def test_rf45_mis_viajes_lista_las_reservas_del_cliente_con_su_detalle(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-45 · HU-27: la pestaña de reservas trae las reservas del cliente con su vuelo, sus

    viajeros, la silla, el estado, el precio y el vencimiento; las de otro cliente no salen.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_lista")
    otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_otro")
    primera_vuelo = _vuelo(db)
    segunda_vuelo = _vuelo(db, 1)
    primera = _reservar(db, cliente.id, primera_vuelo, "1020306001")
    segunda = _reservar(db, cliente.id, segunda_vuelo, "1020306002")
    ajena = _reservar(db, otro.id, primera_vuelo, "1020306003")

    pagina = service.listar_mis_viajes(db, cliente.id, tipo="reserva", ahora=AHORA)

    assert pagina.total == 2
    assert (pagina.pagina, pagina.por_pagina) == (1, 20)
    assert set(_ids(pagina)) == {primera.id, segunda.id}
    assert ajena.id not in _ids(pagina)
    for viaje, reserva, vuelo in (
        (pagina.items[0], segunda, segunda_vuelo),
        (pagina.items[1], primera, primera_vuelo),
    ):
        assert viaje.id == reserva.id
        assert viaje.tipo == "reserva"
        assert viaje.estado == "vigente"
        assert viaje.codigo == reserva.codigo
        assert viaje.vence_en == reserva.vence_en
        assert viaje.tramos[0].vuelo.codigo == vuelo.codigo
        tiquete = viaje.viajeros[0].tiquetes[0]
        assert tiquete.estado == "reservado"
        assert tiquete.precio == P
        assert tiquete.silla
        assert viaje == service.viaje_de(db, reserva)

    assert service.listar_mis_viajes(db, otro.id, tipo="reserva", ahora=AHORA).total == 1
    assert service.listar_mis_viajes(db, cliente.id, tipo="compra", ahora=AHORA).total == 0


def test_rf45_la_pestana_de_compras_solo_trae_compras_pagadas(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-45 · HU-27: las compras pendientes, soltadas o vencidas no se listan; sí la compra

    directa confirmada y la que nace de pagar una reserva, que además enlaza con su reserva.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_compras")
    _saldo(db, cliente.id)

    directa = service.crear_compra(
        db,
        cliente.id,
        entrada([_vuelo(db)], [viajero("1020307001", email="a@example.com")]),
        ahora=AHORA,
    )
    service.confirmar_compra(db, cliente.id, directa.id, ahora=AHORA)
    soltada = service.crear_compra(
        db,
        cliente.id,
        entrada([_vuelo(db, 1)], [viajero("1020307002", email="b@example.com")]),
        ahora=AHORA,
    )
    service.soltar_compra(db, cliente.id, soltada.id, ahora=AHORA)
    vencida = service.crear_compra(
        db,
        cliente.id,
        entrada([_vuelo(db, 2)], [viajero("1020307003", email="c@example.com")]),
        ahora=AHORA,
    )
    pendiente = service.crear_compra(
        db,
        cliente.id,
        entrada([_vuelo(db, 3)], [viajero("1020307004", email="d@example.com")]),
        ahora=AHORA + timedelta(hours=2),
    )
    assert service.liberar_bloqueos(db, AHORA + timedelta(hours=1)) == 1
    assert (vencida.estado, pendiente.estado) == ("vencida", "pendiente")

    reserva = service.crear_reserva(
        db,
        cliente.id,
        entrada(
            [_vuelo(db, 4)],
            [
                viajero("1020307005", email="e@example.com"),
                viajero("1020307006", email="f@example.com"),
            ],
        ),
        ahora=AHORA,
    )
    primero = service.viaje_de(db, reserva).viajeros[0].id
    _, de_la_reserva = service.pagar_reserva(db, cliente.id, reserva.id, [primero], ahora=AHORA)

    compras = service.listar_mis_viajes(db, cliente.id, tipo="compra", ahora=AHORA)

    assert compras.total == 2
    assert _ids(compras) == [de_la_reserva.id, directa.id]
    assert all(viaje.tipo == "compra" and viaje.estado == "activa" for viaje in compras.items)
    nacida_de_reserva = compras.items[0]
    assert nacida_de_reserva.reserva_id == reserva.id
    assert nacida_de_reserva.codigo == reserva.codigo
    assert nacida_de_reserva.total == P
    assert compras.items[1].reserva_id is None
    assert not {soltada.id, vencida.id, pendiente.id} & set(_ids(compras))

    reservas = service.listar_mis_viajes(db, cliente.id, tipo="reserva", ahora=AHORA)
    assert _ids(reservas) == [reserva.id]
    assert reservas.items[0].compra_id == de_la_reserva.id
    assert reservas.items[0].estado == "vigente"


def test_rf45_filtra_por_estado(db: Session, crear_usuario: Callable[..., Any]) -> None:
    """RF-45 · HU-27: cada estado trae solo lo suyo y un estado del otro tipo no trae nada."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_estado")
    _saldo(db, cliente.id)
    pagada = _reservar(db, cliente.id, _vuelo(db), "1020308001")
    vencida = _reservar(db, cliente.id, _vuelo(db, 1), "1020308002")
    _, compra = service.pagar_reserva(db, cliente.id, pagada.id, ahora=AHORA)
    assert service.vencer_reservas(db, AHORA + timedelta(hours=25)) == 1
    vigente = _reservar(
        db, cliente.id, _vuelo(db, 2), "1020308003", ahora=AHORA + timedelta(hours=12)
    )
    ahora = AHORA + timedelta(hours=26)

    def _estado(tipo: Any, estado: Any) -> PaginaViajes:
        return service.listar_mis_viajes(db, cliente.id, tipo=tipo, estado=estado, ahora=ahora)

    assert _ids(_estado("reserva", "vigente")) == [vigente.id]
    assert _ids(_estado("reserva", "vencida")) == [vencida.id]
    assert _ids(_estado("reserva", "pagada")) == [pagada.id]
    assert _ids(_estado("reserva", None)) == [vigente.id, vencida.id, pagada.id]
    assert _ids(_estado("compra", "activa")) == [compra.id]
    sin_nada = _estado("reserva", "activa")
    assert sin_nada.items == []
    assert sin_nada.total == 0
    assert _estado("compra", "vigente").total == 0


def test_rf45_una_reserva_con_el_plazo_pasado_se_informa_vencida(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-45 · HU-27 · RF-37: una reserva cuyo plazo pasó se informa `vencida` con sus tiquetes

    `vencido` aunque el planificador no haya corrido, y se encola el aviso una sola vez.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_vence")
    reserva = _reservar(db, cliente.id, _vuelo(db), "1020309001")

    pagina = service.listar_mis_viajes(db, cliente.id, tipo="reserva", ahora=reserva.vence_en)

    assert _ids(pagina) == [reserva.id]
    assert pagina.items[0].estado == "vencida"
    assert [t.estado for v in pagina.items[0].viajeros for t in v.tiquetes] == ["vencido"]
    assert reserva.estado == "vencida"
    vigentes = service.listar_mis_viajes(
        db, cliente.id, tipo="reserva", estado="vigente", ahora=reserva.vence_en
    )
    assert vigentes.items == []
    assert vigentes.total == 0

    correos = list(db.scalars(select(CorreoEnCola)))
    assert len(correos) == 1
    assert correos[0].destinatario == cliente.email
    assert reserva.codigo in correos[0].asunto
    assert service.vencer_reservas(db, reserva.vence_en) == 0


def test_rf45_filtra_por_el_dia_de_salida_en_hora_de_colombia(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-45 · HU-27: `desde` y `hasta` comparan el día de salida del primer tramo en hora de

    Colombia: un vuelo que sale el 5 a las 03:00 UTC sale el 4 a las 22:00 en Bogotá.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_dias")
    _saldo(db, cliente.id)
    madrugada = crear_vuelo(db, salida=datetime(2026, 12, 5, 3, 0, tzinfo=UTC))
    mediodia = crear_vuelo(db, salida=datetime(2026, 12, 6, 15, 0, tzinfo=UTC))
    a = _reservar(db, cliente.id, madrugada, "1020310001")
    b = _reservar(db, cliente.id, mediodia, "1020310002")
    _, compra_de_a = service.pagar_reserva(db, cliente.id, a.id, ahora=AHORA)

    def _dias(desde: date | None, hasta: date | None, tipo: Any = "reserva") -> list[int]:
        pagina = service.listar_mis_viajes(
            db, cliente.id, tipo=tipo, desde=desde, hasta=hasta, ahora=AHORA
        )
        return _ids(pagina)

    assert _dias(date(2026, 12, 4), date(2026, 12, 4)) == [a.id]
    assert _dias(date(2026, 12, 5), None) == [b.id]
    assert _dias(date(2026, 12, 5), date(2026, 12, 5)) == []
    assert _dias(None, date(2026, 12, 5)) == [a.id]
    assert _dias(date(2026, 12, 4), date(2026, 12, 6)) == [b.id, a.id]
    assert _dias(date(2026, 12, 4), date(2026, 12, 4), "compra") == [compra_de_a.id]
    assert _dias(date(2026, 12, 5), date(2026, 12, 6), "compra") == []
    pagina = service.listar_mis_viajes(
        db,
        cliente.id,
        tipo="reserva",
        desde=date(2026, 12, 4),
        hasta=date(2026, 12, 6),
        ahora=AHORA,
    )
    assert pagina.total == 2


def test_rf45_hasta_anterior_a_desde_es_rango_invalido(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-45 · HU-27: una fecha final anterior a la inicial responde `rango_invalido`."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_rango")

    with pytest.raises(service.DatosInvalidos) as error:
        service.listar_mis_viajes(
            db,
            cliente.id,
            tipo="reserva",
            desde=date(2026, 12, 10),
            hasta=date(2026, 12, 1),
            ahora=AHORA,
        )

    assert error.value.status_code == 422
    assert error.value.codigo == "rango_invalido"
    assert error.value.mensaje == "Revisa los rangos marcados."
    assert error.value.campos == {"hasta": "La fecha final no puede ser anterior a la inicial."}
    mismo_dia = service.listar_mis_viajes(
        db, cliente.id, tipo="reserva", desde=date(2026, 12, 1), hasta=date(2026, 12, 1)
    )
    assert mismo_dia.total == 0


def test_rf45_pagina_de_la_mas_reciente_a_la_mas_antigua(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-45 · HU-27: las reservas salen de la más reciente a la más antigua, `por_pagina` las

    parte en páginas y `total` cuenta todas, también al pedir una página vacía.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_viajes_paginas")
    reservas = [
        _reservar(db, cliente.id, _vuelo(db, horas), f"102031100{horas}") for horas in range(3)
    ]
    for dias, reserva in enumerate(reservas, start=1):
        reserva.creado_en = AHORA - timedelta(days=4 - dias)
    db.flush()
    r1, r2, r3 = reservas

    def _pagina(numero: int) -> PaginaViajes:
        return service.listar_mis_viajes(
            db, cliente.id, tipo="reserva", pagina=numero, por_pagina=2, ahora=AHORA
        )

    primera, segunda, tercera = _pagina(1), _pagina(2), _pagina(3)
    assert _ids(primera) == [r3.id, r2.id]
    assert _ids(segunda) == [r1.id]
    assert tercera.items == []
    assert [pagina.total for pagina in (primera, segunda, tercera)] == [3, 3, 3]
    assert [pagina.pagina for pagina in (primera, segunda, tercera)] == [1, 2, 3]
    assert {pagina.por_pagina for pagina in (primera, segunda, tercera)} == {2}
