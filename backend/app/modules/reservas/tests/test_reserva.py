"""Reserva de tiquetes (HU-24, HU-26, RF-36 a RF-42, SUP-07)."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.reservas import service
from app.modules.reservas.models import Tramo
from app.modules.reservas.schemas import ViajeEntrada
from app.modules.reservas.tests.apoyo import (
    AHORA,
    SALIDA,
)
from app.modules.reservas.tests.apoyo import (
    cliente_con_perfil as _cliente,
)
from app.modules.reservas.tests.apoyo import (
    cliente_verificado as _cliente_verificado,
)
from app.modules.reservas.tests.apoyo import (
    entrada as _entrada,
)
from app.modules.reservas.tests.apoyo import (
    tiquetes_de as _tiquetes,
)
from app.modules.reservas.tests.apoyo import (
    viajero as _viajero,
)
from app.modules.vuelos.tests.fabricas import crear_vuelo


def test_hu24_crea_la_reserva_vigente_con_codigo_y_precio_congelado(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-36, RF-39: la reserva nace vigente, con código de 6 caracteres, un tramo
    por vuelo y el precio vigente congelado en el tiquete."""
    cliente = _cliente_verificado(db, crear_usuario)
    vuelo = crear_vuelo(db, salida=SALIDA)

    transaccion = service.crear_reserva(db, cliente.id, _entrada([vuelo]), ahora=AHORA)

    assert transaccion.tipo == "reserva"
    assert transaccion.estado == "vigente"
    assert transaccion.codigo is not None
    assert len(transaccion.codigo) == 6
    assert transaccion.vence_en == AHORA + timedelta(hours=24)
    assert transaccion.vence_en is not None

    tiquetes = _tiquetes(db, transaccion)
    assert len(tiquetes) == 1
    assert tiquetes[0].estado == "reservado"
    tramo = db.scalar(select(Tramo).where(Tramo.transaccion_id == transaccion.id))
    assert tramo is not None
    assert tramo.precio == vuelo.precio_economica

    # RF-24: el precio no se recalcula después de reservar.
    vuelo.precio_economica = 999_999
    db.flush()
    viaje = service.viaje_de(db, transaccion)
    assert viaje.total == 280_000
    assert viaje.total_pendiente == 280_000
    assert viaje.tramos[0].vuelo.codigo == vuelo.codigo
    assert viaje.viajeros[0].tiquetes[0].silla
    assert viaje.viajeros[0].tiquetes[0].estado == "reservado"


def test_hu24_una_reserva_10_horas_antes_vence_1_hora_antes_de_la_salida(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-36: una reserva hecha 10 horas antes de un vuelo nacional vence en el
    límite de venta (1 hora antes de la salida), no a las 24 horas."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_10h")
    salida = AHORA + timedelta(hours=10)
    vuelo = crear_vuelo(db, salida=salida)

    transaccion = service.crear_reserva(db, cliente.id, _entrada([vuelo]), ahora=AHORA)

    assert transaccion.vence_en == salida - timedelta(hours=1)


def test_hu24_una_reserva_3_dias_antes_vence_en_24_horas(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-36: una reserva hecha 3 días antes vence a las 24 horas."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_3dias")
    vuelo = crear_vuelo(db, salida=AHORA + timedelta(days=3))

    transaccion = service.crear_reserva(db, cliente.id, _entrada([vuelo]), ahora=AHORA)

    assert transaccion.vence_en == AHORA + timedelta(hours=24)


def test_sup07_no_se_reserva_pasado_el_limite_de_venta(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """SUP-07 · HU-24: un vuelo nacional a 30 minutos de salir ya no se reserva."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_tarde")
    vuelo = crear_vuelo(db, salida=AHORA + timedelta(minutes=30))

    with pytest.raises(service.FueraDePlazo) as error:
        service.crear_reserva(db, cliente.id, _entrada([vuelo]), ahora=AHORA)

    assert error.value.codigo == "fuera_de_plazo"
    assert error.value.status_code == 409
    assert "tramos.0.vuelo_id" in (error.value.campos or {})


def test_hu24_un_vuelo_cancelado_no_esta_a_la_venta(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24: un vuelo cancelado responde `vuelo_no_disponible`."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_cancelado")
    vuelo = crear_vuelo(db, salida=SALIDA, estado="cancelado")

    with pytest.raises(service.VueloNoDisponible) as error:
        service.crear_reserva(db, cliente.id, _entrada([vuelo]), ahora=AHORA)

    assert error.value.codigo == "vuelo_no_disponible"
    assert "tramos.0.vuelo_id" in (error.value.campos or {})


def test_hu24_las_sillas_reservadas_no_estan_disponibles_para_otros(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-36: mientras la reserva vive, sus sillas no las toma otro cliente."""
    uno = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_silla_uno")
    dos = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_silla_dos")
    vuelo = crear_vuelo(db, salida=SALIDA)

    primera = service.crear_reserva(db, uno.id, _entrada([vuelo]), ahora=AHORA)
    segunda = service.crear_reserva(
        db,
        dos.id,
        _entrada([vuelo], [_viajero("1020304051", email="luis@example.com")]),
        ahora=AHORA,
    )

    silla_uno = _tiquetes(db, primera)[0].numero_silla
    silla_dos = _tiquetes(db, segunda)[0].numero_silla
    assert silla_uno != silla_dos
    ocupacion = service.ocupacion_de_vuelos(db, [vuelo.id])[vuelo.id]
    assert ocupacion.reservadas_economica == 2


def test_hu24_tres_viajeros_reciben_tres_sillas_contiguas_de_una_fila(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-41: 3 viajeros en económica de un vuelo nacional vacío reciben un bloque
    contiguo de la misma fila."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_bloque")
    vuelo = crear_vuelo(db, salida=SALIDA)
    viajeros = [
        _viajero("1020304050", email="uno@example.com"),
        _viajero("1020304051", email="dos@example.com"),
        _viajero("1020304052", email="tres@example.com"),
    ]

    transaccion = service.crear_reserva(db, cliente.id, _entrada([vuelo], viajeros), ahora=AHORA)

    sillas = [tiquete.numero_silla for tiquete in _tiquetes(db, transaccion)]
    assert len(sillas) == 3
    assert sillas[1] - sillas[0] == 1
    assert sillas[2] - sillas[1] == 1
    assert len({(silla - 1) // 5 for silla in sillas}) == 1
    assert all(26 <= silla <= 150 for silla in sillas)


def test_hu24_la_ubicacion_del_bloque_cambia_entre_reservas(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-41: repetir la reserva en vuelos vacíos produce bloques en posiciones
    distintas (la ubicación es aleatoria)."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_azar")
    bloques: set[tuple[int, ...]] = set()
    for indice in range(12):
        vuelo = crear_vuelo(db, salida=SALIDA + timedelta(minutes=indice))
        viajeros = [
            _viajero("1020304050", email="uno@example.com"),
            _viajero("1020304051", email="dos@example.com"),
            _viajero("1020304052", email="tres@example.com"),
        ]
        transaccion = service.crear_reserva(
            db, cliente.id, _entrada([vuelo], viajeros), ahora=AHORA
        )
        bloques.add(tuple(tiquete.numero_silla for tiquete in _tiquetes(db, transaccion)))

    assert len(bloques) > 1


def test_hu24_un_unico_viajero_de_16_anios_es_rechazado(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-35: un menor de edad no puede ser el único viajero del vuelo."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_menor")
    vuelo = crear_vuelo(db, salida=SALIDA)
    nacimiento = date(SALIDA.year - 16, SALIDA.month, SALIDA.day)

    with pytest.raises(service.MenorSinAdulto) as error:
        service.crear_reserva(
            db,
            cliente.id,
            _entrada([vuelo], [_viajero(fecha_nacimiento=nacimiento)]),
            ahora=AHORA,
        )

    assert error.value.codigo == "menor_sin_adulto"
    assert "viajeros.0.fecha_nacimiento" in (error.value.campos or {})


def test_hu24_quien_cumple_18_antes_del_vuelo_viaja_solo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-35: la edad se mide a la fecha de salida; quien cumple 18 ese día es adulto."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_18")
    vuelo = crear_vuelo(db, salida=SALIDA)
    nacimiento = date(SALIDA.year - 18, SALIDA.month, SALIDA.day)

    transaccion = service.crear_reserva(
        db,
        cliente.id,
        _entrada([vuelo], [_viajero(fecha_nacimiento=nacimiento)]),
        ahora=AHORA,
    )

    assert transaccion.estado == "vigente"


def test_hu24_un_documento_con_tiquete_activo_se_rechaza_sin_revelar_quien_lo_tiene(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-34: un documento con tiquete activo en el vuelo se rechaza, sin decir quién
    hizo la otra compra."""
    primero = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_doc_uno")
    segundo = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_doc_dos")
    vuelo = crear_vuelo(db, salida=SALIDA)
    service.crear_reserva(db, primero.id, _entrada([vuelo]), ahora=AHORA)

    with pytest.raises(service.ViajeroDuplicado) as error:
        service.crear_reserva(db, segundo.id, _entrada([vuelo]), ahora=AHORA)

    assert error.value.codigo == "viajero_duplicado"
    assert "viajeros.0.numero_documento" in (error.value.campos or {})
    assert "Ana" not in error.value.mensaje
    assert "primero" not in error.value.mensaje.lower()


def test_hu24_un_documento_repetido_en_la_solicitud_se_rechaza(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-34: el mismo documento dos veces en la solicitud también es un duplicado."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_doc_repetido")
    vuelo = crear_vuelo(db, salida=SALIDA)
    viajeros = [
        _viajero("1020304050", email="uno@example.com"),
        _viajero("1020304050", email="dos@example.com"),
    ]

    with pytest.raises(service.ViajeroDuplicado):
        service.crear_reserva(db, cliente.id, _entrada([vuelo], viajeros), ahora=AHORA)


def test_hu02_un_correo_sin_verificar_no_puede_reservar(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-02 · HU-24: el cliente sin correo verificado recibe 403 `correo_no_verificado`."""
    from app.modules.usuarios.service import CorreoNoVerificado

    cliente = _cliente(db, crear_usuario, verificado=False, nombre_usuario="cliente_sin_verificar")
    vuelo = crear_vuelo(db, salida=SALIDA)

    with pytest.raises(CorreoNoVerificado) as error:
        service.crear_reserva(db, cliente.id, _entrada([vuelo]), ahora=AHORA)

    assert error.value.status_code == 403
    assert error.value.codigo == "correo_no_verificado"


def test_hu24_el_sexto_tiquete_del_cliente_en_el_vuelo_se_rechaza(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-32: un cliente con 5 tiquetes activos en el vuelo no puede reservar otro."""
    from app.modules.reservas.tests.fabricas import crear_reserva

    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_limite")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_reserva(db, cliente.id, vuelo, cantidad=5)

    with pytest.raises(service.LimiteDeTiquetes) as error:
        service.crear_reserva(db, cliente.id, _entrada([vuelo]), ahora=AHORA)

    assert error.value.codigo == "limite_tiquetes"


def test_hu24_dos_clases_reciben_un_bloque_en_cada_clase(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · RF-33, RF-41: 2 viajeros en primera y 3 en económica reciben un bloque en
    cada clase."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_clases")
    vuelo = crear_vuelo(db, salida=SALIDA)
    viajeros = [
        _viajero("1020304050", clases=("primera",), email="p1@example.com"),
        _viajero("1020304051", clases=("primera",), email="p2@example.com"),
        _viajero("1020304052", clases=("economica",), email="e1@example.com"),
        _viajero("1020304053", clases=("economica",), email="e2@example.com"),
        _viajero("1020304054", clases=("economica",), email="e3@example.com"),
    ]

    transaccion = service.crear_reserva(db, cliente.id, _entrada([vuelo], viajeros), ahora=AHORA)

    sillas = [tiquete.numero_silla for tiquete in _tiquetes(db, transaccion)]
    primera = sorted(silla for silla in sillas if silla <= 25)
    economica = sorted(silla for silla in sillas if silla > 25)
    assert len(primera) == 2
    assert len(economica) == 3
    assert primera[1] - primera[0] == 1
    assert economica[1] - economica[0] == 1
    assert economica[2] - economica[1] == 1
    assert len({(silla - 1) // 5 for silla in economica}) == 1


def test_hu24_clases_incompletas_se_reportan_en_el_viajero(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-24 · HU-26: una clase por tramo es obligatoria; si falta, el error va en
    `viajeros.N.clases`."""
    from app.core.errors import DatosInvalidos

    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_clases_falta")
    ida = crear_vuelo(db, salida=SALIDA)
    regreso = crear_vuelo(db, origen="BOG", destino="PEI", salida=SALIDA + timedelta(hours=4))
    entrada = ViajeEntrada.model_validate(
        {
            "tramos": [{"vuelo_id": ida.id}, {"vuelo_id": regreso.id}],
            "viajeros": [_viajero(clases=("economica",))],
        }
    )

    with pytest.raises(DatosInvalidos) as error:
        service.crear_reserva(db, cliente.id, entrada, ahora=AHORA)

    assert error.value.codigo == "datos_invalidos"
    assert "viajeros.0.clases" in (error.value.campos or {})


def test_hu26_el_regreso_invalido_se_reporta_antes_que_las_clases_faltantes(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26: el orden de validación del contrato pone el regreso (paso 3) antes que las
    clases por viajero (paso 4)."""
    cliente = _cliente_verificado(db, crear_usuario, nombre_usuario="cliente_orden")
    ida = crear_vuelo(db, salida=SALIDA)
    regreso_desde_el_origen = crear_vuelo(db, salida=SALIDA + timedelta(hours=4))
    entrada = ViajeEntrada.model_validate(
        {
            "tramos": [{"vuelo_id": ida.id}, {"vuelo_id": regreso_desde_el_origen.id}],
            "viajeros": [_viajero(clases=("economica",))],
        }
    )

    with pytest.raises(service.RegresoInvalido) as error:
        service.crear_reserva(db, cliente.id, entrada, ahora=AHORA)

    assert error.value.codigo == "regreso_invalido"
    assert "tramos.1.vuelo_id" in (error.value.campos or {})
