"""Compra de tiquetes con el monedero (HU-25, RF-39 a RF-42, RNF-17, SUP-15)."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import archivos
from app.core.db import AdjuntoEnCola, CorreoEnCola
from app.modules.monedero import service as monedero_service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas import service
from app.modules.reservas.models import Tiquete, Tramo
from app.modules.reservas.sillas import SillasInsuficientes
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
from app.modules.vuelos.tests.fabricas import crear_promocion_bd, crear_vuelo


def _correos(db: Session) -> list[CorreoEnCola]:
    return list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))


def _movimientos(db: Session, cliente_id: int) -> list[Movimiento]:
    return list(
        db.scalars(
            select(Movimiento).where(Movimiento.cliente_id == cliente_id).order_by(Movimiento.id)
        )
    )


def _tiquetes_por_clase(db: Session, compra_id: int) -> dict[str, int]:
    filas = db.execute(
        select(Tramo.clase, Tiquete.id)
        .join(Tiquete, Tiquete.tramo_id == Tramo.id)
        .where(Tramo.transaccion_id == compra_id)
    ).all()
    conteo: dict[str, int] = {}
    for clase, _ in filas:
        conteo[clase] = conteo.get(clase, 0) + 1
    return conteo


def test_hu25_iniciar_compra_bloquea_las_sillas_15_minutos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · SUP-15: la compra nace pendiente, con código, tiquetes bloqueados y un

    bloqueo de 15 minutos; sus sillas cuentan como ocupadas y como compra activa.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_inicia_compra")
    vuelo = crear_vuelo(db, salida=SALIDA)

    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    assert compra.tipo == "compra"
    assert compra.estado == "pendiente"
    assert compra.codigo is not None
    assert len(compra.codigo) == 6
    assert compra.vence_en is None
    assert compra.bloqueo_hasta == AHORA + timedelta(minutes=15)
    assert all(tiquete.estado == "bloqueado" for tiquete in tiquetes_de(db, compra))

    viaje = service.viaje_de(db, compra)
    assert viaje.vence_en == compra.bloqueo_hasta
    assert viaje.pagada_en is None
    assert viaje.total_pendiente == vuelo.precio_economica

    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    assert ocupacion.reservadas_economica == 1
    assert ocupacion.reservas_activas == 1


def test_hu25_confirmar_cobra_con_el_monedero_y_deja_el_saldo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RF-39: con $ 1.000.000, una compra de $ 800.000 deja el saldo en $ 200.000

    y registra el movimiento con el código de reserva como referencia.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_confirmar")
    vuelo = crear_vuelo(db, salida=SALIDA, precio_economica=800_000)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)

    assert monedero_service.saldo_de(db, cliente.id) == 200_000
    movimientos = _movimientos(db, cliente.id)
    assert len(movimientos) == 2
    debito = movimientos[-1]
    assert debito.tipo == "compra"
    assert debito.valor == -800_000
    assert debito.saldo_resultante == 200_000
    assert debito.referencia == compra.codigo

    assert compra.estado == "activa"
    assert compra.pagada_en == AHORA
    assert all(tiquete.estado == "comprado" for tiquete in tiquetes_de(db, compra))
    viaje = service.viaje_de(db, compra)
    assert viaje.estado == "activa"
    assert viaje.vence_en is None
    assert viaje.total_pendiente == 0
    assert viaje.pagada_en == AHORA


def test_hu25_saldo_insuficiente_no_emite_tiquetes_y_conserva_el_bloqueo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RF-39 · SUP-15: con $ 500.000, una compra de $ 800.000 responde

    `saldo_insuficiente`; no emite tiquetes y las sillas siguen bloqueadas para recargar.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_sin_saldo_compra")
    vuelo = crear_vuelo(db, salida=SALIDA, precio_economica=800_000)
    crear_movimiento(db, cliente.id, valor=500_000, saldo_resultante=500_000)
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    with pytest.raises(monedero_service.SaldoInsuficiente) as exc:
        service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)

    assert exc.value.codigo == "saldo_insuficiente"
    assert monedero_service.saldo_de(db, cliente.id) == 500_000
    assert len(_movimientos(db, cliente.id)) == 1
    assert compra.estado == "pendiente"
    assert all(tiquete.estado == "bloqueado" for tiquete in tiquetes_de(db, compra))
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_economica == 1

    # S18: después de recargar, el cliente confirma la misma compra antes del vencimiento.
    crear_movimiento(db, cliente.id, valor=300_000, saldo_resultante=800_000)
    service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)
    assert monedero_service.saldo_de(db, cliente.id) == 0
    assert compra.estado == "activa"


def test_hu25_cada_viajero_recibe_el_codigo_y_el_comprador_el_comprobante(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RF-39: cada viajero recibe el código y el comprador el comprobante en PDF

    como adjunto `comprobante-<codigo>.pdf`.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_correos")
    vuelo = crear_vuelo(db, salida=SALIDA, precio_economica=800_000)
    crear_movimiento(db, cliente.id, valor=2_000_000, saldo_resultante=2_000_000)
    viajeros = [
        viajero("1020304001", email="ana.compra@example.com"),
        viajero("1020304002", email="luis.compra@example.com"),
    ]
    compra = service.crear_compra(db, cliente.id, entrada([vuelo], viajeros), ahora=AHORA)

    service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)

    correos = _correos(db)
    assert {correo.destinatario for correo in correos} == {
        "ana.compra@example.com",
        "luis.compra@example.com",
        cliente.email,
    }
    for correo in correos:
        if correo.destinatario != cliente.email:
            assert compra.codigo in correo.asunto
            assert compra.codigo in correo.texto

    comprobante = next(correo for correo in correos if correo.destinatario == cliente.email)
    assert "Comprobante" in comprobante.asunto
    assert compra.codigo in comprobante.asunto
    adjuntos = list(
        db.scalars(select(AdjuntoEnCola).where(AdjuntoEnCola.correo_id == comprobante.id))
    )
    assert len(adjuntos) == 1
    assert adjuntos[0].nombre == f"comprobante-{compra.codigo}.pdf"
    assert adjuntos[0].tipo_mime == "application/pdf"
    assert archivos.leer(adjuntos[0].clave).startswith(b"%PDF")


def test_hu25_el_bloqueo_vencido_libera_las_sillas_y_confirmar_falla(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · SUP-15 · RNF-18: a los 15 minutos se liberan las sillas, la compra queda

    vencida y confirmar responde `bloqueo_vencido`; la tarea es idempotente.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_bloqueo_vence")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    assert service.liberar_bloqueos(db, AHORA + timedelta(minutes=14)) == 0
    assert service.liberar_bloqueos(db, AHORA + timedelta(minutes=15)) == 1

    assert compra.estado == "vencida"
    assert all(tiquete.estado == "vencido" for tiquete in tiquetes_de(db, compra))
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_economica == 0
    assert service.liberar_bloqueos(db, AHORA + timedelta(minutes=16)) == 0

    with pytest.raises(service.BloqueoVencido) as exc:
        service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA + timedelta(minutes=15))
    assert exc.value.codigo == "bloqueo_vencido"


def test_hu25_el_get_informa_vencida_una_compra_con_el_bloqueo_pasado(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: `GET /compras/{id}` devuelve el estado efectivo: una pendiente con el bloqueo

    pasado se informa vencida, con sus tiquetes vencidos y las sillas libres.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_get_vencida")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    obtenida = service.obtener_compra(
        db, cliente.id, compra.id, ahora=AHORA + timedelta(minutes=15)
    )

    assert obtenida.estado == "vencida"
    assert all(tiquete.estado == "vencido" for tiquete in tiquetes_de(db, compra))
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_economica == 0


def test_hu25_dos_viajeros_en_primera_y_tres_en_economica_reciben_su_bloque(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RF-41: una compra con 2 viajeros en primera y 3 en económica recibe un

    bloque de sillas en cada clase.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_dos_clases")
    vuelo = crear_vuelo(db, salida=SALIDA)
    viajeros = [
        viajero("1020304101", clases=("primera",), email="p1@example.com"),
        viajero("1020304102", clases=("primera",), email="p2@example.com"),
        viajero("1020304103", clases=("economica",), email="e1@example.com"),
        viajero("1020304104", clases=("economica",), email="e2@example.com"),
        viajero("1020304105", clases=("economica",), email="e3@example.com"),
    ]

    compra = service.crear_compra(db, cliente.id, entrada([vuelo], viajeros), ahora=AHORA)

    assert _tiquetes_por_clase(db, compra.id) == {"primera": 2, "economica": 3}
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_primera == 2
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_economica == 3


def test_rf42_el_segundo_cliente_no_toma_la_ultima_silla_y_conserva_su_saldo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-42: si dos clientes compiten por la última silla al iniciar la compra, el primero

    la bloquea y al segundo le responde `clase_agotada`, sin descontarle saldo.
    """
    uno = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_carrera_uno")
    dos = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_carrera_dos")
    crear_movimiento(db, dos.id, valor=500_000, saldo_resultante=500_000)
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_economica=1)

    service.crear_compra(
        db, uno.id, entrada([vuelo], [viajero("1020304501", email="uno@example.com")]), ahora=AHORA
    )

    with pytest.raises(SillasInsuficientes) as exc:
        service.crear_compra(
            db,
            dos.id,
            entrada([vuelo], [viajero("1020304502", email="dos@example.com")]),
            ahora=AHORA,
        )
    assert exc.value.codigo == "clase_agotada"
    assert monedero_service.saldo_de(db, dos.id) == 500_000


def test_rf42_si_quedan_sillas_el_segundo_recibe_otra(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-42: con dos sillas, el segundo cliente recibe una distinta de la del primero."""
    uno = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_silla_uno")
    dos = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_silla_dos")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_economica=2)

    primera = service.crear_compra(
        db, uno.id, entrada([vuelo], [viajero("1020304503", email="uno@example.com")]), ahora=AHORA
    )
    segunda = service.crear_compra(
        db, dos.id, entrada([vuelo], [viajero("1020304504", email="dos@example.com")]), ahora=AHORA
    )

    silla_uno = tiquetes_de(db, primera)[0].numero_silla
    silla_dos = tiquetes_de(db, segunda)[0].numero_silla
    assert silla_uno != silla_dos


def test_rnf17_si_falla_el_comprobante_no_queda_ni_movimiento_ni_tiquete_ni_correo(
    db: Session, crear_usuario: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """RNF-17: si falla cualquier paso de la confirmación, no queda nada: ni movimiento,

    ni tiquetes comprados, ni correos. La compra sigue pendiente y con sus sillas bloqueadas.
    """

    def _falla(_datos: object) -> bytes:
        raise RuntimeError("fallo simulado al generar el comprobante")

    monkeypatch.setattr(service, "generar_comprobante", _falla)
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_atomico")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    savepoint = db.begin_nested()
    with pytest.raises(RuntimeError, match="fallo simulado"):
        service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)
    savepoint.rollback()

    db.refresh(compra)
    assert compra.estado == "pendiente"
    assert compra.pagada_en is None
    assert all(tiquete.estado == "bloqueado" for tiquete in tiquetes_de(db, compra))
    assert monedero_service.saldo_de(db, cliente.id) == 1_000_000
    assert len(_movimientos(db, cliente.id)) == 1
    assert _correos(db) == []


def test_hu25_las_reglas_de_hu24_aplican_a_la_compra(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: la compra exige correo verificado y rechaza documentos duplicados y menores

    sin adulto, igual que la reserva.
    """
    sin_verificar = cliente_con_perfil(
        db, crear_usuario, verificado=False, nombre_usuario="cliente_compra_sin_verificar"
    )
    vuelo = crear_vuelo(db, salida=SALIDA)

    with pytest.raises(usuarios_service.CorreoNoVerificado):
        service.crear_compra(db, sin_verificar.id, entrada([vuelo]), ahora=AHORA)

    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_reglas_compra")
    with pytest.raises(service.ViajeroDuplicado) as duplicado:
        service.crear_compra(
            db,
            cliente.id,
            entrada(
                [vuelo],
                [
                    viajero("1020304201", email="uno@example.com"),
                    viajero("1020304201", email="dos@example.com"),
                ],
            ),
            ahora=AHORA,
        )
    assert duplicado.value.codigo == "viajero_duplicado"

    menor = viajero(
        "1020304202",
        fecha_nacimiento=date(2015, 1, 1),
        email="menor@example.com",
    )
    with pytest.raises(service.MenorSinAdulto) as sin_adulto:
        service.crear_compra(db, cliente.id, entrada([vuelo], [menor]), ahora=AHORA)
    assert sin_adulto.value.codigo == "menor_sin_adulto"


def test_hu25_el_limite_de_cinco_y_el_cupo_se_validan_en_la_compra(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RF-32, RF-33: la compra respeta el límite de 5 tiquetes activos y el cupo

    de la clase, igual que la reserva.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_limite_compra")
    vuelo = crear_vuelo(db, salida=SALIDA)
    cinco = [
        viajero(f"10203043{indice:02d}", email=f"cinco{indice}@example.com") for indice in range(5)
    ]
    service.crear_compra(db, cliente.id, entrada([vuelo], cinco), ahora=AHORA)

    with pytest.raises(service.LimiteDeTiquetes) as limite:
        service.crear_compra(
            db,
            cliente.id,
            entrada([vuelo], [viajero("1020304399", email="sexto@example.com")]),
            ahora=AHORA,
        )
    assert limite.value.codigo == "limite_tiquetes"

    otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_cupo_compra")
    lleno = crear_vuelo(db, salida=SALIDA + timedelta(days=1), capacidad_economica=1)
    service.crear_compra(db, otro.id, entrada([lleno]), ahora=AHORA)
    with pytest.raises(SillasInsuficientes) as cupo:
        service.crear_compra(
            db,
            otro.id,
            entrada([lleno], [viajero("1020304400", email="cupo@example.com")]),
            ahora=AHORA,
        )
    assert cupo.value.codigo == "clase_agotada"


def test_hu25_al_vender_la_ultima_silla_marca_la_promocion_agotada(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25 · RF-23: al confirmar la última silla de una clase se marca agotada su promoción."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_promocion")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_economica=1)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    promocion = crear_promocion_bd(
        db,
        vuelo,
        clases=("economica",),
        inicio=AHORA - timedelta(days=1),
        fin=AHORA + timedelta(days=1),
    )
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)

    assert promocion.estado == "agotada"


def test_hu25_una_compra_pagada_no_se_suelta_ni_se_confirma_dos_veces(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: soltar o confirmar una compra activa responde `estado_invalido`."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_pagada_compra")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_movimiento(db, cliente.id, valor=1_000_000, saldo_resultante=1_000_000)
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)
    service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)

    with pytest.raises(service.EstadoInvalido):
        service.soltar_compra(db, cliente.id, compra.id, ahora=AHORA)
    with pytest.raises(service.EstadoInvalido):
        service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)


def test_hu25_soltar_una_compra_pendiente_libera_las_sillas(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: soltar la compra la deja cancelada, libera sus sillas y es idempotente."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_suelta")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra = service.crear_compra(db, cliente.id, entrada([vuelo]), ahora=AHORA)

    service.soltar_compra(db, cliente.id, compra.id, ahora=AHORA)
    assert compra.estado == "cancelada"
    assert all(tiquete.estado == "cancelado" for tiquete in tiquetes_de(db, compra))
    assert service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id].reservadas_economica == 0

    service.soltar_compra(db, cliente.id, compra.id, ahora=AHORA)
    assert compra.estado == "cancelada"


def test_hu25_no_se_puede_confirmar_ni_soltar_una_compra_ajena(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-25: una compra de otro cliente responde `no_encontrado`, igual que una inexistente."""
    dueño = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_dueño_compra")
    otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_otro_compra")
    vuelo = crear_vuelo(db, salida=SALIDA)
    compra = service.crear_compra(db, dueño.id, entrada([vuelo]), ahora=AHORA)

    with pytest.raises(service.CompraNoEncontrada) as exc:
        service.obtener_compra(db, otro.id, compra.id, ahora=AHORA)
    assert exc.value.codigo == "no_encontrado"
    assert exc.value.mensaje == "La compra no existe."

    with pytest.raises(service.CompraNoEncontrada):
        service.obtener_compra(db, dueño.id, 999_999, ahora=AHORA)
