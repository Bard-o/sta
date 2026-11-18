"""Pago de una reserva, completa o por viajero (HU-27, RF-35, RF-38, RF-39, RNF-17, SUP-40).

Pagar una reserva crea una única compra con el mismo código; los tiquetes pagados pasan a los
tramos de esa compra con su silla y los demás siguen reservados con el mismo vencimiento.
"""

import io
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import archivos
from app.core.db import AdjuntoEnCola, CorreoEnCola
from app.modules.monedero import service as monedero_service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas import service
from app.modules.reservas.models import Tiquete, Tramo, Transaccion
from app.modules.reservas.schemas import Viaje
from app.modules.reservas.tests.apoyo import (
    AHORA,
    SALIDA,
    cliente_con_perfil,
    cliente_verificado,
    entrada,
    tiquetes_de,
    viajero,
)
from app.modules.usuarios import service as usuarios_service
from app.modules.vuelos import service as vuelos_service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import crear_promocion_bd, crear_vuelo

# Precio de la clase económica de `crear_vuelo`.
P = 280_000


def _saldo(db: Session, cliente_id: int, valor: int) -> None:
    crear_movimiento(db, cliente_id, valor=valor, saldo_resultante=valor)


def _viajeros(cantidad: int, *, clases: tuple[str, ...] = ("economica",)) -> list[dict[str, Any]]:
    """Viajeros con documento y correo distintos, para reservar `cantidad` tiquetes."""
    return [
        viajero(
            f"10203{indice:05d}",
            clases=clases,
            nombres=f"Viajero{'abcdefgh'[indice]}",
            email=f"viajero{indice}@example.com",
        )
        for indice in range(cantidad)
    ]


def _reservar(
    db: Session,
    cliente_id: int,
    vuelos: list[Vuelo],
    viajeros: list[dict[str, Any]] | None = None,
    *,
    ahora: datetime = AHORA,
) -> Transaccion:
    return service.crear_reserva(db, cliente_id, entrada(vuelos, viajeros), ahora=ahora)


def _ids_de_viajeros(db: Session, reserva: Transaccion) -> list[int]:
    return [viajero.id for viajero in service.viaje_de(db, reserva).viajeros]


def _correos(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def _movimientos(db: Session, cliente_id: int) -> list[Movimiento]:
    return list(
        db.scalars(
            select(Movimiento).where(Movimiento.cliente_id == cliente_id).order_by(Movimiento.id)
        )
    )


def _compras_de(db: Session, reserva: Transaccion) -> list[Transaccion]:
    return list(db.scalars(select(Transaccion).where(Transaccion.reserva_id == reserva.id)))


def _estados(viaje: Viaje) -> list[str]:
    return sorted(tiquete.estado for viajero in viaje.viajeros for tiquete in viajero.tiquetes)


def _texto_del_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    return re.sub(r"\s+", " ", " ".join(pagina.extract_text() or "" for pagina in lector.pages))


# ---------- Precio, pago parcial y vencimiento ----------


def test_hu27_el_pago_cobra_el_precio_congelado_aunque_haya_promocion(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-38: una promoción posterior a la reserva no cambia lo que se paga: se cobra

    el precio congelado y el débito lleva el código de la reserva como referencia.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_congelado")
    vuelo = crear_vuelo(db, salida=SALIDA, precio_economica=300_000)
    _saldo(db, cliente.id, 1_000_000)
    reserva = _reservar(db, cliente.id, [vuelo])
    crear_promocion_bd(db, vuelo, porcentaje=20, inicio=AHORA, fin=AHORA + timedelta(days=2))
    momento = AHORA + timedelta(hours=1)
    precio = vuelos_service.precio_vigente(db, vuelo.id, "economica", ahora=momento)
    assert precio.precio == 240_000

    _, compra = service.pagar_reserva(db, cliente.id, reserva.id, ahora=momento)

    debito = _movimientos(db, cliente.id)[-1]
    assert debito.tipo == "compra"
    assert debito.valor == -300_000
    assert debito.referencia == reserva.codigo
    assert monedero_service.saldo_de(db, cliente.id) == 700_000
    assert service.viaje_de(db, compra).total == 300_000


def test_hu27_pagar_2_de_4_viajeros_deja_2_comprados_y_2_reservados_con_el_mismo_vencimiento(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · SUP-40: pagar 2 de 4 viajeros crea la compra con el mismo código y deja los

    otros 2 reservados con el vencimiento de siempre; las sillas no se mueven.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_parcial")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 2_000_000)
    reserva = _reservar(db, cliente.id, [vuelo], _viajeros(4))
    vence_en = reserva.vence_en
    ids = _ids_de_viajeros(db, reserva)
    momento = AHORA + timedelta(hours=2)

    devuelta, compra = service.pagar_reserva(db, cliente.id, reserva.id, ids[:2], ahora=momento)

    assert devuelta is reserva
    assert reserva.estado == "vigente"
    assert reserva.vence_en == vence_en
    vista_reserva = service.viaje_de(db, reserva)
    assert _estados(vista_reserva) == ["comprado", "comprado", "reservado", "reservado"]
    assert [
        tiquete.estado for viajero in vista_reserva.viajeros[:2] for tiquete in viajero.tiquetes
    ] == ["comprado", "comprado"]
    assert vista_reserva.total == 4 * P
    assert vista_reserva.total_pendiente == 2 * P
    assert vista_reserva.compra_id == compra.id
    assert vista_reserva.reserva_id is None
    assert vista_reserva.pagada_en is None

    assert compra.tipo == "compra"
    assert compra.estado == "activa"
    assert compra.codigo == reserva.codigo
    assert compra.reserva_id == reserva.id
    vista_compra = service.viaje_de(db, compra)
    assert vista_compra.tipo == "compra"
    assert vista_compra.reserva_id == reserva.id
    assert vista_compra.compra_id is None
    assert [viajero.id for viajero in vista_compra.viajeros] == ids[:2]
    assert _estados(vista_compra) == ["comprado", "comprado"]
    assert vista_compra.total == 2 * P
    assert vista_compra.total_pendiente == 0
    assert vista_compra.vence_en is None
    assert vista_compra.pagada_en == momento

    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    assert ocupacion.vendidas_economica == 2
    assert ocupacion.reservadas_economica == 2
    assert ocupacion.reservas_activas == 1
    assert service.tiquetes_activos_en_vuelo(db, cliente.id, vuelo.id) == 4


def test_hu27_al_vencer_la_reserva_solo_vencen_los_viajeros_sin_pagar(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-37: al vencer una reserva pagada en parte, los 2 tiquetes sin pagar vencen y

    liberan sus sillas; los 2 pagados siguen comprados en su compra.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_vence")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 2_000_000)
    reserva = _reservar(db, cliente.id, [vuelo], _viajeros(4))
    ids = _ids_de_viajeros(db, reserva)
    _, compra = service.pagar_reserva(
        db, cliente.id, reserva.id, ids[:2], ahora=AHORA + timedelta(hours=1)
    )

    assert service.vencer_reservas(db, reserva.vence_en) == 1

    assert reserva.estado == "vencida"
    vista_reserva = service.viaje_de(db, reserva)
    assert _estados(vista_reserva) == ["comprado", "comprado", "vencido", "vencido"]
    assert vista_reserva.compra_id == compra.id
    assert compra.estado == "activa"
    assert _estados(service.viaje_de(db, compra)) == ["comprado", "comprado"]

    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    assert ocupacion.vendidas_economica == 2
    assert ocupacion.reservadas_economica == 0
    assert ocupacion.reservas_activas == 0
    avisos = [correo for correo in _correos(db) if "venció" in correo.asunto]
    assert len(avisos) == 1
    assert avisos[0].destinatario == cliente.email
    assert service.vencer_reservas(db, reserva.vence_en) == 0


def test_hu27_los_pagos_siguientes_se_suman_a_la_misma_compra_y_la_reserva_queda_pagada(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-39: los pagos de una reserva se acumulan en una sola compra; cuando no queda

    ningún viajero reservado la reserva pasa a `pagada` y ya no se puede volver a pagar.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_dos_veces")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 2_000_000)
    reserva = _reservar(db, cliente.id, [vuelo], _viajeros(4))
    vence_en = reserva.vence_en
    ids = _ids_de_viajeros(db, reserva)
    primer_pago = AHORA + timedelta(hours=1)
    segundo_pago = AHORA + timedelta(hours=3)

    _, compra = service.pagar_reserva(db, cliente.id, reserva.id, ids[:2], ahora=primer_pago)
    assert compra.pagada_en == primer_pago
    assert reserva.estado == "vigente"
    _, misma = service.pagar_reserva(db, cliente.id, reserva.id, None, ahora=segundo_pago)

    assert misma.id == compra.id
    assert len(_compras_de(db, reserva)) == 1
    assert compra.pagada_en == segundo_pago
    vista_compra = service.viaje_de(db, compra)
    assert [viajero.id for viajero in vista_compra.viajeros] == ids
    assert vista_compra.total == 4 * P
    assert vista_compra.total_pendiente == 0
    assert _estados(vista_compra) == ["comprado"] * 4

    assert reserva.estado == "pagada"
    assert reserva.vence_en == vence_en
    vista_reserva = service.viaje_de(db, reserva)
    assert vista_reserva.total_pendiente == 0
    assert vista_reserva.total == 4 * P
    assert vista_reserva.compra_id == compra.id
    debitos = [m for m in _movimientos(db, cliente.id) if m.tipo == "compra"]
    assert [m.valor for m in debitos] == [-2 * P, -2 * P]
    assert {m.referencia for m in debitos} == {reserva.codigo}
    assert monedero_service.saldo_de(db, cliente.id) == 2_000_000 - 4 * P
    assert service.vencer_reservas(db, vence_en + timedelta(days=1)) == 0

    with pytest.raises(service.ReservaNoVigente):
        service.pagar_reserva(db, cliente.id, reserva.id, ahora=segundo_pago)


def test_hu27_las_sillas_de_la_reserva_son_las_de_la_compra(
    db: Session, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-27 · RF-41: pagar no reasigna sillas: cada tiquete conserva su id y su silla en un

    trayecto completo con clases distintas, y la compra copia un tramo por orden y clase.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_sillas")
    ida = crear_vuelo(db, salida=SALIDA)
    regreso = crear_vuelo(db, origen="BOG", destino="PEI", salida=ida.llegada + timedelta(hours=2))
    _saldo(db, cliente.id, 5_000_000)
    reserva = _reservar(
        db,
        cliente.id,
        [ida, regreso],
        [
            viajero("1020300001", clases=("primera", "economica"), email="a@example.com"),
            viajero("1020300002", clases=("economica", "economica"), email="b@example.com"),
        ],
    )

    def _sillas(viaje: Viaje) -> dict[tuple[int, int], tuple[int, str, int]]:
        return {
            (viajero.id, tiquete.tramo): (tiquete.id, tiquete.silla, tiquete.numero_silla)
            for viajero in viaje.viajeros
            for tiquete in viajero.tiquetes
        }

    antes = _sillas(service.viaje_de(db, reserva))
    assert len(antes) == 4

    def _falla(*_args: object, **_kwargs: object) -> list[int]:
        raise AssertionError("pagar una reserva no reasigna sillas")

    monkeypatch.setattr(service, "asignar_sillas", _falla)
    primero, segundo = _ids_de_viajeros(db, reserva)
    _, compra = service.pagar_reserva(db, cliente.id, reserva.id, [primero], ahora=AHORA)
    service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)

    assert _sillas(service.viaje_de(db, compra)) == antes
    assert _sillas(service.viaje_de(db, reserva)) == antes
    assert all(tiquete.estado == "comprado" for tiquete in tiquetes_de(db, compra))
    assert tiquetes_de(db, reserva) == []
    tramos = list(db.scalars(select(Tramo).where(Tramo.transaccion_id == compra.id)))
    assert sorted((tramo.orden, tramo.clase) for tramo in tramos) == [
        (1, "economica"),
        (1, "primera"),
        (2, "economica"),
    ]
    assert {tramo.precio for tramo in tramos if tramo.clase == "primera"} == {750_000}

    for vuelo, primera, economica in ((ida, 1, 1), (regreso, 0, 2)):
        ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
        assert (ocupacion.vendidas_primera, ocupacion.vendidas_economica) == (primera, economica)
        assert (ocupacion.reservadas_primera, ocupacion.reservadas_economica) == (0, 0)
    assert [viajero.id for viajero in service.viaje_de(db, compra).viajeros] == [primero, segundo]


# ---------- Reservas que no se pagan ----------


def test_hu27_no_se_paga_una_reserva_vencida_o_cancelada(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27: pagar una reserva vencida, con el plazo pasado o cancelada responde

    `reserva_no_vigente` sin cobrar ni crear la compra.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_no_vigente")
    _saldo(db, cliente.id, 5_000_000)

    def _no_se_paga(reserva: Transaccion, ahora: datetime) -> None:
        with pytest.raises(service.ReservaNoVigente) as error:
            service.pagar_reserva(db, cliente.id, reserva.id, ahora=ahora)
        assert error.value.status_code == 409
        assert error.value.codigo == "reserva_no_vigente"
        assert error.value.mensaje == (
            "La reserva ya no está vigente: venció, se canceló o ya está pagada."
        )
        assert _compras_de(db, reserva) == []
        assert len(_movimientos(db, cliente.id)) == 1
        assert monedero_service.saldo_de(db, cliente.id) == 5_000_000

    vencida_vuelo = crear_vuelo(db, salida=SALIDA)
    vencida = _reservar(db, cliente.id, [vencida_vuelo])
    assert service.vencer_reservas(db, vencida.vence_en) == 1
    _no_se_paga(vencida, AHORA + timedelta(hours=1))

    plazo_vuelo = crear_vuelo(db, salida=SALIDA + timedelta(hours=1))
    con_plazo_pasado = _reservar(db, cliente.id, [plazo_vuelo])
    _no_se_paga(con_plazo_pasado, con_plazo_pasado.vence_en)
    assert con_plazo_pasado.estado == "vigente"

    cancelada_vuelo = crear_vuelo(db, salida=SALIDA + timedelta(hours=2))
    cancelada = _reservar(db, cliente.id, [cancelada_vuelo])
    assert service.anular_reservas_de_vuelo(db, cancelada_vuelo.id) == 1
    assert cancelada.estado == "cancelada"
    _no_se_paga(cancelada, AHORA + timedelta(hours=1))


def test_hu27_con_saldo_insuficiente_no_toca_la_reserva(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-39: con $ 100.000 de saldo, pagar una reserva de $ 280.000 responde

    `saldo_insuficiente` sin tocar la reserva; tras recargar lo que falta, el pago pasa.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_sin_saldo")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 100_000)
    reserva = _reservar(db, cliente.id, [vuelo])
    vence_en = reserva.vence_en

    with pytest.raises(monedero_service.SaldoInsuficiente) as error:
        service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)

    assert error.value.codigo == "saldo_insuficiente"
    assert "te faltan $ 180.000" in error.value.mensaje
    assert reserva.estado == "vigente"
    assert reserva.vence_en == vence_en
    assert all(tiquete.estado == "reservado" for tiquete in tiquetes_de(db, reserva))
    assert _compras_de(db, reserva) == []
    assert len(_movimientos(db, cliente.id)) == 1
    assert _correos(db) == []

    crear_movimiento(db, cliente.id, tipo="recarga", valor=180_000, saldo_resultante=280_000)
    _, compra = service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)

    assert compra.estado == "activa"
    assert reserva.estado == "pagada"
    assert monedero_service.saldo_de(db, cliente.id) == 0


# ---------- Correos, comprobante y promociones ----------


def test_hu27_el_pago_envia_el_codigo_a_los_pagados_y_el_comprobante_con_lo_pagado(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-39: al pagar 2 de 3 viajeros, cada pagado recibe el código, el tercero no, y el

    comprador recibe el comprobante en PDF solo con lo pagado en esa operación.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_correos")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 2_000_000)
    reserva = _reservar(db, cliente.id, [vuelo], _viajeros(3))
    ids = _ids_de_viajeros(db, reserva)
    assert _correos(db) == []

    _, compra = service.pagar_reserva(db, cliente.id, reserva.id, ids[:2], ahora=AHORA)

    correos = _correos(db)
    assert {correo.destinatario for correo in correos} == {
        "viajero0@example.com",
        "viajero1@example.com",
        cliente.email,
    }
    for correo in correos:
        if correo.destinatario != cliente.email:
            assert compra.codigo in correo.asunto
            assert compra.codigo in correo.texto
    comprobante = next(correo for correo in correos if correo.destinatario == cliente.email)
    adjuntos = list(
        db.scalars(select(AdjuntoEnCola).where(AdjuntoEnCola.correo_id == comprobante.id))
    )
    assert len(adjuntos) == 1
    assert adjuntos[0].nombre == f"comprobante-{compra.codigo}.pdf"
    contenido = archivos.leer(adjuntos[0].clave)
    assert contenido.startswith(b"%PDF")
    texto = _texto_del_pdf(contenido)
    assert "Viajeroa" in texto
    assert "Viajerob" in texto
    assert "Viajeroc" not in texto
    assert "560.000" in texto

    service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)
    nuevos = _correos(db)[len(correos) :]
    assert {correo.destinatario for correo in nuevos} == {"viajero2@example.com", cliente.email}


def test_rf23_al_pagar_la_ultima_silla_se_marca_la_promocion_agotada(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-23: al pagar la última silla de una clase se marca agotada su promoción."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_promocion")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_economica=1)
    _saldo(db, cliente.id, 1_000_000)
    reserva = _reservar(db, cliente.id, [vuelo])
    promocion = crear_promocion_bd(
        db,
        vuelo,
        clases=("economica",),
        inicio=AHORA - timedelta(days=1),
        fin=AHORA + timedelta(days=1),
    )
    assert promocion.estado != "agotada"

    service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)

    assert promocion.estado == "agotada"


def test_rnf17_si_falla_el_comprobante_el_pago_no_deja_nada(
    db: Session, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-27 · RNF-17: si falla cualquier paso del pago, no queda nada: ni movimiento, ni

    compra, ni tiquetes comprados, ni correos. La reserva sigue vigente.
    """

    def _falla(_datos: object) -> bytes:
        raise RuntimeError("fallo simulado al generar el comprobante")

    monkeypatch.setattr(service, "generar_comprobante", _falla)
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_atomico")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 1_000_000)
    reserva = _reservar(db, cliente.id, [vuelo], _viajeros(2))
    ids = _ids_de_viajeros(db, reserva)

    savepoint = db.begin_nested()
    with pytest.raises(RuntimeError, match="fallo simulado"):
        service.pagar_reserva(db, cliente.id, reserva.id, ids, ahora=AHORA)
    savepoint.rollback()

    db.refresh(reserva)
    assert reserva.estado == "vigente"
    assert all(tiquete.estado == "reservado" for tiquete in tiquetes_de(db, reserva))
    assert _compras_de(db, reserva) == []
    assert monedero_service.saldo_de(db, cliente.id) == 1_000_000
    assert len(_movimientos(db, cliente.id)) == 1
    assert _correos(db) == []


# ---------- Menores y viajeros elegidos ----------


def test_hu27_un_menor_no_queda_solo_en_la_compra(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-35: un menor que se paga necesita un adulto ya pagado o pagado en esa misma

    operación; si no, `menor_sin_adulto` con `campos.viajero_ids` y no cambia nada.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_menor")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 2_000_000)
    reserva = _reservar(
        db,
        cliente.id,
        [vuelo],
        [
            viajero("1020301001", nombres="Adulto", email="adulto@example.com"),
            viajero(
                "1020301002",
                nombres="Menor",
                fecha_nacimiento=date(2015, 1, 1),
                email="menor@example.com",
            ),
        ],
    )
    adulto, menor = _ids_de_viajeros(db, reserva)

    with pytest.raises(service.MenorSinAdulto) as error:
        service.pagar_reserva(db, cliente.id, reserva.id, [menor], ahora=AHORA)

    assert error.value.status_code == 422
    assert error.value.codigo == "menor_sin_adulto"
    assert error.value.campos == {"viajero_ids": service._MENOR_SOLO_EN_COMPRA}
    assert _estados(service.viaje_de(db, reserva)) == ["reservado", "reservado"]
    assert _compras_de(db, reserva) == []
    assert len(_movimientos(db, cliente.id)) == 1

    service.pagar_reserva(db, cliente.id, reserva.id, [adulto], ahora=AHORA)
    assert reserva.estado == "vigente"
    service.pagar_reserva(db, cliente.id, reserva.id, [menor], ahora=AHORA)
    assert reserva.estado == "pagada"

    # Junto con el adulto, en la misma operación, el menor también se paga.
    otro_vuelo = crear_vuelo(db, salida=SALIDA + timedelta(hours=1))
    otra = _reservar(
        db,
        cliente.id,
        [otro_vuelo],
        [
            viajero("1020301003", nombres="Adulto", email="adulto2@example.com"),
            viajero(
                "1020301004",
                nombres="Menor",
                fecha_nacimiento=date(2015, 1, 1),
                email="menor2@example.com",
            ),
        ],
    )
    service.pagar_reserva(db, cliente.id, otra.id, ahora=AHORA)
    assert otra.estado == "pagada"


def test_hu27_viajeros_ajenos_repetidos_o_ya_pagados_son_datos_invalidos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27: un viajero de otra reserva, repetido, ya pagado o una lista vacía responde

    `datos_invalidos` con `campos.viajero_ids`, sin cobrar nada.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_invalidos")
    vuelo = crear_vuelo(db, salida=SALIDA)
    otro_vuelo = crear_vuelo(db, salida=SALIDA + timedelta(hours=1))
    _saldo(db, cliente.id, 2_000_000)
    reserva = _reservar(db, cliente.id, [vuelo], _viajeros(2))
    ajena = _reservar(
        db, cliente.id, [otro_vuelo], [viajero("1020302999", email="otro@example.com")]
    )
    primero, segundo = _ids_de_viajeros(db, reserva)
    (de_la_ajena,) = _ids_de_viajeros(db, ajena)
    service.pagar_reserva(db, cliente.id, reserva.id, [primero], ahora=AHORA)

    for viajero_ids in ([de_la_ajena], [segundo, segundo], [primero], [segundo, primero], []):
        with pytest.raises(service.DatosInvalidos) as error:
            service.pagar_reserva(db, cliente.id, reserva.id, viajero_ids, ahora=AHORA)
        assert error.value.status_code == 422
        assert error.value.codigo == "datos_invalidos"
        assert error.value.campos == {"viajero_ids": service._VIAJEROS_NO_PAGABLES}

    assert len([m for m in _movimientos(db, cliente.id) if m.tipo == "compra"]) == 1
    assert reserva.estado == "vigente"


# ---------- Quién puede pagar ----------


def test_hu27_la_reserva_de_otro_cliente_o_una_compra_no_existen(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27: pagar la reserva de otro cliente, una compra o un id inexistente responde

    `no_encontrado`; el 404 va antes que la verificación del correo.
    """
    dueno = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_dueno")
    otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_otro")
    sin_verificar = cliente_con_perfil(
        db, crear_usuario, verificado=False, nombre_usuario="cliente_paga_sin_verificar"
    )
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, otro.id, 1_000_000)
    reserva = _reservar(db, dueno.id, [vuelo])
    compra = service.crear_compra(
        db,
        otro.id,
        entrada([vuelo], [viajero("1020302001", email="otra@example.com")]),
        ahora=AHORA,
    )

    for cliente_id, reserva_id in (
        (otro.id, reserva.id),
        (otro.id, compra.id),
        (otro.id, 999_999),
        (sin_verificar.id, reserva.id),
    ):
        with pytest.raises(service.ReservaNoEncontrada) as error:
            service.pagar_reserva(db, cliente_id, reserva_id, ahora=AHORA)
        assert error.value.status_code == 404
        assert error.value.codigo == "no_encontrado"
        assert error.value.mensaje == "La reserva no existe."

    assert reserva.estado == "vigente"
    assert _compras_de(db, reserva) == []


def test_hu02_pagar_una_reserva_exige_el_correo_verificado(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-02 · HU-27: un cliente sin el correo verificado no paga ni su propia reserva."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_verificacion")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 1_000_000)
    reserva = _reservar(db, cliente.id, [vuelo])
    cliente.email_verificado = False
    db.flush()

    with pytest.raises(usuarios_service.CorreoNoVerificado) as error:
        service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)

    assert error.value.status_code == 403
    assert error.value.codigo == "correo_no_verificado"
    assert reserva.estado == "vigente"
    assert _compras_de(db, reserva) == []


# ---------- La compra de la reserva ----------


def test_hu27_la_compra_de_la_reserva_se_consulta_como_cualquier_compra(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · HU-25: la compra que nace de pagar una reserva se consulta como una compra

    activa: no se confirma ni se suelta, y cuenta como tiquete activo futuro del cliente.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_consulta")
    vuelo = crear_vuelo(db, salida=datetime.now(UTC) + timedelta(days=30))
    _saldo(db, cliente.id, 1_000_000)
    reserva = _reservar(db, cliente.id, [vuelo])
    _, compra = service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)

    consultada = service.obtener_compra(db, cliente.id, compra.id, ahora=AHORA)
    assert consultada.id == compra.id
    assert consultada.estado == "activa"
    with pytest.raises(service.EstadoInvalido):
        service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)
    with pytest.raises(service.EstadoInvalido):
        service.soltar_compra(db, cliente.id, compra.id, ahora=AHORA)
    assert compra.estado == "activa"
    assert all(tiquete.estado == "comprado" for tiquete in tiquetes_de(db, compra))

    activos = service.tiquetes_activos_futuros_de_cliente(db, cliente.id)
    assert [(activo.tipo, activo.codigo_reserva) for activo in activos] == [
        ("compra", reserva.codigo)
    ]
    assert [pasajero.numero_silla for pasajero in service.pasajeros_de_vuelo(db, vuelo.id)] == [
        tiquete.numero_silla for tiquete in tiquetes_de(db, compra)
    ]


def test_hu27_anular_el_vuelo_no_cancela_una_reserva_que_se_pago_mientras_tanto(
    db: Session, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-16 · HU-27: si una reserva se paga entre elegir las reservas a anular y bloquearlas,

    la anulación la salta: no queda cancelada con un cobro hecho ni se cuenta ni se avisa.
    """
    # Otro test vuelve a importar `vuelos.service`: se toma el módulo vigente, el que usa `service`.
    from app.modules.vuelos import service as vuelos_vigente

    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_y_anula")
    otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_solo_anulada")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 1_000_000)
    pagada = _reservar(db, cliente.id, [vuelo])
    anulable = _reservar(db, otro.id, [vuelo], [viajero("1020303001", email="otro@example.com")])
    detalle_real = vuelos_vigente.obtener_vuelo_detalle

    def _se_paga_tras_bloquear(*args: Any, **kwargs: Any) -> Any:
        # La anulación ya eligió y bloqueó las filas: ahora la reserva queda pagada.
        pagada.estado = "pagada"
        return detalle_real(*args, **kwargs)

    monkeypatch.setattr(vuelos_vigente, "obtener_vuelo_detalle", _se_paga_tras_bloquear)

    anuladas = service.anular_reservas_de_vuelo(db, vuelo.id)

    assert anuladas == 1
    assert pagada.estado == "pagada"
    assert anulable.estado == "cancelada"
    assert all(tiquete.estado == "reservado" for tiquete in tiquetes_de(db, pagada))
    assert [correo.destinatario for correo in _correos(db)] == [otro.email]


def test_hu27_un_documento_pagado_sigue_ocupando_el_vuelo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-27 · RF-34: el documento de un viajero pagado sigue siendo duplicado en el vuelo,

    aunque su tiquete ya viva en la compra y no en la reserva.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_paga_documento")
    otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_documento_repetido")
    vuelo = crear_vuelo(db, salida=SALIDA)
    _saldo(db, cliente.id, 1_000_000)
    reserva = _reservar(db, cliente.id, [vuelo], [viajero("1020304999", email="uno@example.com")])
    service.pagar_reserva(db, cliente.id, reserva.id, ahora=AHORA)

    with pytest.raises(service.ViajeroDuplicado):
        service.crear_reserva(
            db,
            otro.id,
            entrada([vuelo], [viajero("1020304999", email="otro@example.com")]),
            ahora=AHORA,
        )
    total = db.scalar(select(func.count()).select_from(Tiquete).where(Tiquete.vuelo_id == vuelo.id))
    assert total == 1
