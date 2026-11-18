"""Concurrencia de las compras con hilos y conexiones reales (HU-25, RF-41, RF-42, RF-48,
RNF-17, SUP-13).

Cada hilo hace lo mismo que `POST /compras` y `POST /compras/{id}/confirmar` (router.py):
llama al service con su propia sesión y confirma. La fixture `base_confirmada`
(app/core/testing.py) da la sesión por hilo y borra lo confirmado.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST, BaseConfirmada
from app.modules.monedero import service as monedero_service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas import service
from app.modules.reservas.models import ESTADOS_TIQUETE_ACTIVOS, Tiquete, Tramo, Transaccion
from app.modules.reservas.schemas import ViajeEntrada
from app.modules.reservas.tests import fabricas
from app.modules.reservas.tests.apoyo import (
    AHORA,
    SALIDA,
    cliente_verificado,
    entrada,
    tiquetes_de,
    viajero,
)
from app.modules.usuarios import service as usuarios_service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import crear_vuelo

HILOS = 50  # HU-25, RNF-17
SALDO = 1_000_000
ULTIMA_SILLA = 150  # Apéndice A: económica nacional va de 26 a 150


@dataclass(frozen=True)
class Intento:
    """Resultado de lo que hizo un hilo: la compra que logró y el código del error, si falló."""

    cliente_id: int
    compra_id: int | None = None
    codigo: str | None = None  # None = éxito; si no, el `codigo` del error del contrato

    @property
    def exito(self) -> bool:
        return self.codigo is None


def _creador_de_usuarios(sesion: Session) -> Callable[..., Any]:
    """Lo mismo que la fixture `crear_usuario`, con una sesión que confirma de verdad."""

    def _crear(
        rol: Rol = Rol.CLIENTE,
        *,
        nombre_usuario: str | None = None,
        contrasena: str = CONTRASENA_TEST,
        email: str | None = None,
    ) -> Any:
        return usuarios_service.crear_usuario(
            sesion,
            nombre_usuario=nombre_usuario or f"{rol.value}_test",
            contrasena=contrasena,
            rol=rol,
            email=email,
        )

    return _crear


def _clientes(sesion: Session, prefijo: str, cantidad: int, *, saldo: int = 0) -> list[int]:
    """Clientes verificados, con `saldo` en el monedero si se pide. Quien llama hace commit."""
    crear = _creador_de_usuarios(sesion)
    ids = []
    for indice in range(cantidad):
        cliente = cliente_verificado(sesion, crear, nombre_usuario=f"{prefijo}_{indice:02d}")
        if saldo > 0:
            crear_movimiento(sesion, cliente.id, valor=saldo, saldo_resultante=saldo)
        ids.append(cliente.id)
    return ids


def _vuelo_con_libres(sesion: Session, libres: int, **cambios: Any) -> Vuelo:
    """Vuelo nacional con una compra activa que deja libres las últimas `libres` sillas."""
    vuelo = crear_vuelo(sesion, salida=SALIDA, **cambios)
    ocupadas = vuelo.capacidad_economica - libres
    if ocupadas > 0:
        (ocupante,) = _clientes(sesion, "conc_ocupante", 1)
        fabricas.crear_compra(sesion, ocupante, vuelo, cantidad=ocupadas, estado="activa")
    return vuelo


def _iniciar_y_confirmar(cliente_id: int, cuerpo: ViajeEntrada, sesion: Session) -> Intento:
    """`POST /compras` y, si queda la compra, `POST /compras/{id}/confirmar`."""
    try:
        compra = service.crear_compra(sesion, cliente_id, cuerpo, ahora=AHORA)
        sesion.commit()
    except AppError as error:
        sesion.rollback()
        return Intento(cliente_id, codigo=error.codigo)
    try:
        service.confirmar_compra(sesion, cliente_id, compra.id, ahora=AHORA)
        sesion.commit()
    except AppError as error:
        sesion.rollback()
        return Intento(cliente_id, compra.id, error.codigo)
    return Intento(cliente_id, compra.id)


def _iniciar(cliente_id: int, cuerpo: ViajeEntrada, sesion: Session) -> Intento:
    """Solo `POST /compras`: la compra queda pendiente con sus sillas bloqueadas."""
    try:
        compra = service.crear_compra(sesion, cliente_id, cuerpo, ahora=AHORA)
        sesion.commit()
    except AppError as error:
        sesion.rollback()
        return Intento(cliente_id, codigo=error.codigo)
    return Intento(cliente_id, compra.id)


def _confirmar(cliente_id: int, compra_id: int, sesion: Session) -> Intento:
    """Solo `POST /compras/{id}/confirmar` sobre una compra ya iniciada."""
    try:
        service.confirmar_compra(sesion, cliente_id, compra_id, ahora=AHORA)
        sesion.commit()
    except AppError as error:
        sesion.rollback()
        return Intento(cliente_id, compra_id, error.codigo)
    return Intento(cliente_id, compra_id)


def _debitar(cliente_id: int, valor: int, referencia: str, sesion: Session) -> str | None:
    """Débito del monedero; devuelve el código del error o None si se cobró."""
    try:
        monedero_service.debitar(sesion, cliente_id, valor, referencia=referencia)
        sesion.commit()
    except AppError as error:
        sesion.rollback()
        return error.codigo
    return None


def _sillas_repetidas(sesion: Session, vuelo_id: int) -> list[tuple[int, int]]:
    """RF-41: sillas con más de un tiquete activo en el vuelo (debe ser ninguna)."""
    filas = sesion.execute(
        select(Tiquete.numero_silla, func.count())
        .where(Tiquete.vuelo_id == vuelo_id, Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS))
        .group_by(Tiquete.numero_silla)
        .having(func.count() > 1)
    )
    return [(silla, veces) for silla, veces in filas]


def _tiquetes_activos(sesion: Session, vuelo_id: int) -> int:
    consulta = select(func.count()).where(
        Tiquete.vuelo_id == vuelo_id, Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS)
    )
    return sesion.execute(consulta).scalar_one()


def _descuadres(sesion: Session, cliente_ids: list[int]) -> list[Any]:
    """RF-48: movimientos cuyo saldo resultante no es la suma acumulada de los movimientos."""
    acumulado = func.sum(Movimiento.valor).over(
        partition_by=Movimiento.cliente_id, order_by=Movimiento.id
    )
    filas = (
        select(
            Movimiento.id,
            Movimiento.cliente_id,
            Movimiento.saldo_resultante,
            acumulado.label("acumulado"),
        )
        .where(Movimiento.cliente_id.in_(cliente_ids))
        .subquery()
    )
    return list(
        sesion.execute(
            select(filas.c.id, filas.c.saldo_resultante, filas.c.acumulado)
            .where(filas.c.saldo_resultante != filas.c.acumulado)
            .order_by(filas.c.id)
        )
    )


def _movimientos(sesion: Session, cliente_id: int) -> list[Movimiento]:
    return list(
        sesion.scalars(
            select(Movimiento).where(Movimiento.cliente_id == cliente_id).order_by(Movimiento.id)
        )
    )


def _transacciones_de(sesion: Session, cliente_id: int) -> int:
    consulta = (
        select(func.count()).select_from(Transaccion).where(Transaccion.cliente_id == cliente_id)
    )
    return sesion.execute(consulta).scalar_one()


def _sillas_libres(sesion: Session, vuelo: Vuelo) -> set[int]:
    """Sillas de la cabina económica nacional (26 a 150) sin tiquete activo.

    El mapa sigue el Apéndice A, no `capacidad_economica`: esa capacidad solo limita cuántas
    se venden (`validar_cupo`).
    """
    todas = set(range(vuelo.capacidad_primera + 1, ULTIMA_SILLA + 1))
    ocupadas = set(
        sesion.scalars(
            select(Tiquete.numero_silla).where(
                Tiquete.vuelo_id == vuelo.id, Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS)
            )
        )
    )
    return todas - ocupadas


@pytest.mark.parametrize(
    ("escenario", "sillas_en_el_mapa"),
    [
        ("ultima_silla_de_la_cabina", 1),  # 124 de 125 ocupadas: queda libre la 150
        ("cupo_de_una_silla", 125),  # capacidad_economica=1: una venta, silla sorteada en 26-150
    ],
    ids=["ultima_silla_de_la_cabina", "cupo_de_una_silla"],
)
def test_hu25_de_50_compras_simultaneas_por_la_ultima_silla_solo_una_tiene_exito(
    base_confirmada: BaseConfirmada, escenario: str, sillas_en_el_mapa: int
) -> None:
    """HU-25 · RF-42 · RNF-17 · SUP-13: con 50 compras simultáneas por la última silla,

    exactamente una tiene éxito y a las demás se les informa `clase_agotada` sin descontarles
    saldo.
    """
    with base_confirmada.sesion() as sesion:
        if escenario == "ultima_silla_de_la_cabina":
            vuelo = _vuelo_con_libres(sesion, libres=1)
        else:
            vuelo = crear_vuelo(sesion, salida=SALIDA, capacidad_economica=1)
        clientes = _clientes(sesion, "conc_ultima", HILOS, saldo=SALDO)
        sesion.commit()
        libres_antes = _sillas_libres(sesion, vuelo)
        activos_antes = _tiquetes_activos(sesion, vuelo.id)
        precio = vuelo.precio_economica
    assert len(libres_antes) == sillas_en_el_mapa
    assert ULTIMA_SILLA in libres_antes

    cuerpos = [
        entrada([vuelo], [viajero(f"55{indice:08d}", email=f"ultima{indice}@example.com")])
        for indice in range(HILOS)
    ]
    intentos = base_confirmada.en_paralelo(
        [
            partial(_iniciar_y_confirmar, cliente, cuerpo)
            for cliente, cuerpo in zip(clientes, cuerpos, strict=True)
        ]
    )

    ganadores = [intento for intento in intentos if intento.exito]
    perdedores = [intento for intento in intentos if not intento.exito]
    assert len(ganadores) == 1
    assert Counter(intento.codigo for intento in perdedores) == {"clase_agotada": HILOS - 1}

    with base_confirmada.sesion() as sesion:
        (ganador,) = ganadores
        compra = sesion.get_one(Transaccion, ganador.compra_id)
        assert compra.estado == "activa"
        tiquetes = tiquetes_de(sesion, compra)
        assert [tiquete.estado for tiquete in tiquetes] == ["comprado"]
        assert tiquetes[0].numero_silla in libres_antes
        assert monedero_service.saldo_de(sesion, ganador.cliente_id) == SALDO - precio

        for perdedor in perdedores:
            assert monedero_service.saldo_de(sesion, perdedor.cliente_id) == SALDO
            assert len(_movimientos(sesion, perdedor.cliente_id)) == 1
            assert _transacciones_de(sesion, perdedor.cliente_id) == 0

        # RF-41: ninguna silla con dos tiquetes activos y un solo tiquete nuevo en el vuelo.
        assert _sillas_repetidas(sesion, vuelo.id) == []
        assert _tiquetes_activos(sesion, vuelo.id) == activos_antes + 1
        # RF-48: el saldo resultante de cada movimiento es la suma acumulada.
        assert _descuadres(sesion, clientes) == []


def test_rf41_compras_simultaneas_por_las_ultimas_sillas_nunca_repiten_silla(
    base_confirmada: BaseConfirmada,
) -> None:
    """RF-41 · SUP-13: 20 compras simultáneas de 2 viajeros por las 10 últimas sillas: 5 las

    obtienen, ninguna silla queda asignada dos veces ni se asigna una ocupada, y a las demás se
    les informa `clase_agotada`.
    """
    compradores = 20
    with base_confirmada.sesion() as sesion:
        vuelo = _vuelo_con_libres(sesion, libres=10)
        clientes = _clientes(sesion, "conc_pares", compradores)
        sesion.commit()
        libres_antes = _sillas_libres(sesion, vuelo)
        activos_antes = _tiquetes_activos(sesion, vuelo.id)
    assert libres_antes == set(range(141, 151))

    cuerpos = [
        entrada(
            [vuelo],
            [
                viajero(f"56{indice:04d}{pareja:04d}", email=f"pareja{indice}_{pareja}@example.com")
                for pareja in range(2)
            ],
        )
        for indice in range(compradores)
    ]
    intentos = base_confirmada.en_paralelo(
        [
            partial(_iniciar, cliente, cuerpo)
            for cliente, cuerpo in zip(clientes, cuerpos, strict=True)
        ]
    )

    assert Counter(intento.codigo for intento in intentos) == {None: 5, "clase_agotada": 15}
    ganadoras = [intento.compra_id for intento in intentos if intento.exito]

    with base_confirmada.sesion() as sesion:
        sillas = sesion.scalars(
            select(Tiquete.numero_silla)
            .join(Tramo, Tiquete.tramo_id == Tramo.id)
            .where(Tramo.transaccion_id.in_(ganadoras))
        )
        assert sorted(sillas) == sorted(libres_antes)
        for compra_id in ganadoras:
            compra = sesion.get_one(Transaccion, compra_id)
            assert [tiquete.estado for tiquete in tiquetes_de(sesion, compra)] == ["bloqueado"] * 2
        assert _sillas_repetidas(sesion, vuelo.id) == []
        assert _tiquetes_activos(sesion, vuelo.id) == activos_antes + 10


def test_rf48_dos_confirmaciones_simultaneas_no_dejan_el_saldo_negativo(
    base_confirmada: BaseConfirmada,
) -> None:
    """RF-48 · RNF-17: con $ 100.000, dos compras de $ 70.000 confirmadas a la vez: solo una

    se cobra, el saldo nunca queda negativo y la suma de los movimientos cuadra; la otra
    responde `saldo_insuficiente` y conserva sus sillas bloqueadas (HU-25).
    """
    clientes_con_saldo = 5
    with base_confirmada.sesion() as sesion:
        vuelo = crear_vuelo(sesion, salida=SALIDA, precio_economica=70_000)
        clientes = _clientes(sesion, "conc_saldo", clientes_con_saldo, saldo=100_000)
        sesion.commit()
        compras: list[tuple[int, int]] = []
        for indice, cliente in enumerate(clientes):
            for pareja in range(2):
                cuerpo = entrada(
                    [vuelo],
                    [
                        viajero(
                            f"57{indice:04d}{pareja:04d}",
                            email=f"saldo{indice}_{pareja}@example.com",
                        )
                    ],
                )
                compra = service.crear_compra(sesion, cliente, cuerpo, ahora=AHORA)
                compras.append((cliente, compra.id))
        sesion.commit()

    intentos = base_confirmada.en_paralelo(
        [partial(_confirmar, cliente, compra_id) for cliente, compra_id in compras]
    )

    with base_confirmada.sesion() as sesion:
        for cliente in clientes:
            suyos = [intento for intento in intentos if intento.cliente_id == cliente]
            assert Counter(intento.codigo for intento in suyos) == {
                None: 1,
                "saldo_insuficiente": 1,
            }
            assert monedero_service.saldo_de(sesion, cliente) == 30_000
            assert [
                (movimiento.tipo, movimiento.valor, movimiento.saldo_resultante)
                for movimiento in _movimientos(sesion, cliente)
            ] == [("recarga", 100_000, 100_000), ("compra", -70_000, 30_000)]

            (perdedor,) = [intento for intento in suyos if not intento.exito]
            compra = sesion.get_one(Transaccion, perdedor.compra_id)
            assert compra.estado == "pendiente"
            assert [tiquete.estado for tiquete in tiquetes_de(sesion, compra)] == ["bloqueado"]
        assert _descuadres(sesion, clientes) == []


def test_rf48_debitos_simultaneos_sobre_el_mismo_saldo_cuadran_con_los_movimientos(
    base_confirmada: BaseConfirmada,
) -> None:
    """RF-48 · RNF-17: 10 débitos simultáneos de $ 100.000 sobre $ 350.000: pasan exactamente 3,

    el saldo queda en $ 50.000 y nunca es negativo, y cada saldo resultante es la suma
    acumulada de los movimientos.
    """
    with base_confirmada.sesion() as sesion:
        (cliente,) = _clientes(sesion, "conc_debito", 1, saldo=350_000)
        sesion.commit()

    codigos = base_confirmada.en_paralelo(
        [partial(_debitar, cliente, 100_000, f"CONC{indice:02d}") for indice in range(10)]
    )

    assert Counter(codigos) == {None: 3, "saldo_insuficiente": 7}
    with base_confirmada.sesion() as sesion:
        assert monedero_service.saldo_de(sesion, cliente) == 50_000
        movimientos = _movimientos(sesion, cliente)
        assert all(movimiento.saldo_resultante >= 0 for movimiento in movimientos)
        debitos = [m.saldo_resultante for m in movimientos if m.tipo == "compra"]
        assert debitos == [250_000, 150_000, 50_000]
        assert _descuadres(sesion, [cliente]) == []


def test_base_confirmada_borra_lo_que_la_prueba_confirmo(base_confirmada: BaseConfirmada) -> None:
    """#129: lo que una prueba de concurrencia confirma no queda para los demás tests: después

    de limpiar, cada tabla tiene las mismas filas que al empezar.
    """
    with base_confirmada.sesion() as sesion:
        (cliente,) = _clientes(sesion, "conc_limpieza", 1, saldo=SALDO)
        vuelo = crear_vuelo(sesion, salida=SALIDA)
        sesion.commit()
        compra = service.crear_compra(sesion, cliente, entrada([vuelo]), ahora=AHORA)
        sesion.commit()
        service.confirmar_compra(sesion, cliente, compra.id, ahora=AHORA)
        sesion.commit()

    tablas = {
        "usuarios",
        "vuelos",
        "transacciones",
        "tramos",
        "viajeros",
        "tiquetes",
        "movimientos",
        "cola_correos",
        "cola_correos_adjuntos",
    }
    assert tablas <= base_confirmada.filas_nuevas().keys()

    base_confirmada.limpiar()

    assert base_confirmada.filas_nuevas() == {}
    with base_confirmada.sesion() as sesion:
        assert monedero_service.saldo_de(sesion, cliente) == 0
        assert _transacciones_de(sesion, cliente) == 0
