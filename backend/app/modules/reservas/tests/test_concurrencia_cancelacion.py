"""Concurrencia entre cancelar o editar un vuelo y sus ventas (HU-15, HU-16, HU-24, HU-25,
HU-27, RF-18, RF-19, RNF-17).

Cada prueba fuerza el orden en vez de esperar a que lo decida el sistema operativo: una sesión
hace la primera operación sin confirmar (con sus locks tomados), la segunda corre en otro hilo
hasta quedar esperando un lock en PostgreSQL y solo entonces la primera confirma. Así se prueba
cada lado de la carrera. La fixture `base_confirmada` (app/core/testing.py) da sesiones que
confirman de verdad y borra lo confirmado al terminar.
"""

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from datetime import time as hora
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import Rol
from app.core.testing import CONTRASENA_TEST, BaseConfirmada
from app.modules.monedero import service as monedero_service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas import service
from app.modules.reservas.models import ESTADOS_TIQUETE_ACTIVOS, Tiquete, Tramo, Transaccion
from app.modules.reservas.tests.apoyo import AHORA, SALIDA, cliente_verificado, entrada, tiquetes_de
from app.modules.usuarios import service as usuarios_service
from app.modules.vuelos import service as vuelos_service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.schemas import VueloEntrada
from app.modules.vuelos.tests.fabricas import crear_vuelo

ESPERA = 10  # s máximos para que la segunda operación llegue a esperar un lock o termine
SALDO = 1_000_000
PRECIO = 280_000  # precio económico por defecto de `crear_vuelo`

Operacion = Callable[[Session], Any]


def _creador(sesion: Session) -> Callable[..., Any]:
    """Lo mismo que la fixture `crear_usuario`, con una sesión que confirma de verdad."""

    def _crear(
        rol: Rol = Rol.CLIENTE,
        *,
        nombre_usuario: str,
        contrasena: str = CONTRASENA_TEST,
        email: str | None = None,
    ) -> Any:
        return usuarios_service.crear_usuario(
            sesion, nombre_usuario=nombre_usuario, contrasena=contrasena, rol=rol, email=email
        )

    return _crear


def _escenario(sesion: Session, nombre: str) -> tuple[Vuelo, int, int]:
    """Vuelo programado, un cliente verificado con saldo y un administrador. Confirma."""
    crear = _creador(sesion)
    vuelo = crear_vuelo(sesion, salida=SALIDA)
    cliente = cliente_verificado(sesion, crear, nombre_usuario=f"conc_{nombre}")
    crear_movimiento(sesion, cliente.id, valor=SALDO, saldo_resultante=SALDO)
    admin = crear(Rol.ADMIN, nombre_usuario=f"conc_{nombre}_admin")
    sesion.commit()
    return vuelo, cliente.id, admin.id


def _intentar(operacion: Operacion, sesion: Session) -> str | None:
    """Corre la operación y confirma, como el endpoint; devuelve el `codigo` del error o None."""
    try:
        operacion(sesion)
        sesion.commit()
    except AppError as error:
        sesion.rollback()
        return error.codigo
    return None


def _esperar_lock(base: BaseConfirmada, pid: int, futuro: Future[Any]) -> None:
    """Espera a que la conexión `pid` quede esperando un lock; falla si el hilo termina antes."""
    limite = time.monotonic() + ESPERA
    while time.monotonic() < limite:
        if futuro.done():
            raise AssertionError(f"La segunda operación no esperó ningún lock: {futuro.result()!r}")
        # Conexión nueva en cada vuelta: pg_stat_activity se congela dentro de una transacción.
        with base.engine.connect() as conexion:
            espera = conexion.execute(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            ).scalar_one_or_none()
        if espera == "Lock":
            return
        time.sleep(0.02)
    raise AssertionError("La segunda operación no llegó a esperar un lock.")


def _en_orden(base: BaseConfirmada, primera: Operacion, segunda: Operacion) -> str | None:
    """`primera` toma sus locks sin confirmar; `segunda` corre en otro hilo hasta esperarlos.

    Cuando la segunda ya espera, la primera confirma. Devuelve el `codigo` del error de la
    segunda, o None si tuvo éxito. Si algo falla, la sesión de la primera se cierra (y suelta
    sus locks) antes de esperar al hilo, para que la prueba nunca se quede colgada.
    """
    pid_listo: Future[int] = Future()

    def _hilo() -> str | None:
        with base.sesion() as sesion:
            pid_listo.set_result(sesion.execute(text("SELECT pg_backend_pid()")).scalar_one())
            return _intentar(segunda, sesion)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="concurrencia-vuelo") as pool:
        with base.sesion() as sesion:
            primera(sesion)
            futuro = pool.submit(_hilo)
            _esperar_lock(base, pid_listo.result(timeout=ESPERA), futuro)
            sesion.commit()
        return futuro.result(timeout=ESPERA)


def _cancelar(vuelo_id: int, admin_id: int) -> Operacion:
    return lambda sesion: vuelos_service.cancelar_vuelo(
        sesion, vuelo_id, usuario_id=admin_id, ahora=AHORA
    )


def _iniciar(tipo: str, cliente_id: int, vuelo: Vuelo) -> Operacion:
    """`POST /compras` o `POST /reservas` con un viajero en económica."""
    crear = service.crear_compra if tipo == "compra" else service.crear_reserva
    cuerpo = entrada([vuelo])
    return lambda sesion: crear(sesion, cliente_id, cuerpo, ahora=AHORA)


def _pagar(tipo: str, cliente_id: int, transaccion_id: int) -> Operacion:
    """`POST /compras/{id}/confirmar` o `POST /reservas/{id}/pagar`."""
    if tipo == "compra":
        return lambda sesion: service.confirmar_compra(
            sesion, cliente_id, transaccion_id, ahora=AHORA
        )
    return lambda sesion: service.pagar_reserva(sesion, cliente_id, transaccion_id, ahora=AHORA)


def _ventas_abiertas(sesion: Session, vuelo_id: int) -> list[tuple[str, str]]:
    """Transacciones del vuelo pendientes, vigentes o activas, como (tipo, estado)."""
    consulta = (
        select(Transaccion.tipo, Transaccion.estado)
        .join(Tramo, Tramo.transaccion_id == Transaccion.id)
        .where(
            Tramo.vuelo_id == vuelo_id,
            Transaccion.estado.in_(("pendiente", "vigente", "activa")),
        )
        .distinct()
    )
    return [(tipo, estado) for tipo, estado in sesion.execute(consulta)]


def _tiquetes_activos(sesion: Session, vuelo_id: int) -> int:
    consulta = select(func.count()).where(
        Tiquete.vuelo_id == vuelo_id, Tiquete.estado.in_(ESTADOS_TIQUETE_ACTIVOS)
    )
    return sesion.execute(consulta).scalar_one()


def _movimientos(sesion: Session, cliente_id: int) -> list[tuple[str, int]]:
    consulta = (
        select(Movimiento.tipo, Movimiento.valor)
        .where(Movimiento.cliente_id == cliente_id)
        .order_by(Movimiento.id)
    )
    return [(tipo, valor) for tipo, valor in sesion.execute(consulta)]


def _transaccion_de(sesion: Session, cliente_id: int, tipo: str) -> Transaccion:
    return sesion.scalars(
        select(Transaccion).where(Transaccion.cliente_id == cliente_id, Transaccion.tipo == tipo)
    ).one()


@pytest.mark.parametrize("tipo", ["compra", "reserva"])
def test_hu16_cancelar_primero_rechaza_la_venta_que_espera(
    base_confirmada: BaseConfirmada, tipo: str
) -> None:
    """HU-16 · RF-19 · HU-24 · HU-25: si la cancelación del vuelo va primero, la compra o la
    reserva que llega mientras tanto espera, ve el vuelo cancelado y responde
    `vuelo_no_disponible`: no queda ninguna venta abierta ni tiquete activo en el vuelo.
    """
    with base_confirmada.sesion() as sesion:
        vuelo, cliente, admin = _escenario(sesion, f"cancela_antes_{tipo}")

    codigo = _en_orden(base_confirmada, _cancelar(vuelo.id, admin), _iniciar(tipo, cliente, vuelo))

    assert codigo == "vuelo_no_disponible"
    with base_confirmada.sesion() as sesion:
        assert sesion.get_one(Vuelo, vuelo.id).estado == "cancelado"
        assert _ventas_abiertas(sesion, vuelo.id) == []
        assert _tiquetes_activos(sesion, vuelo.id) == 0


@pytest.mark.parametrize("tipo", ["compra", "reserva"])
def test_hu16_la_venta_iniciada_primero_se_anula_al_cancelar(
    base_confirmada: BaseConfirmada, tipo: str
) -> None:
    """HU-16 · RF-19: si la compra o la reserva se inicia primero, la cancelación espera a que
    confirme, la ve y la anula: queda `cancelada` con sus tiquetes cancelados y sin cobro.
    """
    with base_confirmada.sesion() as sesion:
        vuelo, cliente, admin = _escenario(sesion, f"inicia_antes_{tipo}")

    codigo = _en_orden(base_confirmada, _iniciar(tipo, cliente, vuelo), _cancelar(vuelo.id, admin))

    assert codigo is None
    with base_confirmada.sesion() as sesion:
        assert sesion.get_one(Vuelo, vuelo.id).estado == "cancelado"
        transaccion = _transaccion_de(sesion, cliente, tipo)
        assert transaccion.estado == "cancelada"
        assert [tiquete.estado for tiquete in tiquetes_de(sesion, transaccion)] == ["cancelado"]
        assert _ventas_abiertas(sesion, vuelo.id) == []
        assert _tiquetes_activos(sesion, vuelo.id) == 0
        assert _movimientos(sesion, cliente) == [("recarga", SALDO)]


@pytest.mark.parametrize("tipo", ["compra", "reserva"])
def test_hu16_pagar_primero_impide_cancelar_el_vuelo(
    base_confirmada: BaseConfirmada, tipo: str
) -> None:
    """HU-16 · RF-19 · HU-25 · HU-27 · RNF-17: si la confirmación de la compra o el pago de la
    reserva va primero, la cancelación espera, ve el tiquete vendido y responde
    `vuelo_con_tiquetes`: el vuelo sigue programado con su venta cobrada.
    """
    with base_confirmada.sesion() as sesion:
        vuelo, cliente, admin = _escenario(sesion, f"paga_antes_{tipo}")
        abierta = _iniciar(tipo, cliente, vuelo)(sesion)
        sesion.commit()

    codigo = _en_orden(
        base_confirmada, _pagar(tipo, cliente, abierta.id), _cancelar(vuelo.id, admin)
    )

    assert codigo == "vuelo_con_tiquetes"
    with base_confirmada.sesion() as sesion:
        assert sesion.get_one(Vuelo, vuelo.id).estado == "programado"
        compra = _transaccion_de(sesion, cliente, "compra")
        assert compra.estado == "activa"
        assert [tiquete.estado for tiquete in tiquetes_de(sesion, compra)] == ["comprado"]
        if tipo == "reserva":
            assert sesion.get_one(Transaccion, abierta.id).estado == "pagada"
        assert monedero_service.saldo_de(sesion, cliente) == SALDO - PRECIO


@pytest.mark.parametrize(
    ("tipo", "error"),
    [("compra", "bloqueo_vencido"), ("reserva", "reserva_no_vigente")],
)
def test_hu16_cancelar_primero_rechaza_el_pago_sin_cobrar(
    base_confirmada: BaseConfirmada, tipo: str, error: str
) -> None:
    """HU-16 · HU-25 · HU-27 · RNF-17: si la cancelación va primero, confirmar la compra o pagar
    la reserva espera, la encuentra `cancelada` y responde con el error del contrato sin
    descontar saldo.
    """
    with base_confirmada.sesion() as sesion:
        vuelo, cliente, admin = _escenario(sesion, f"cancela_antes_pago_{tipo}")
        abierta = _iniciar(tipo, cliente, vuelo)(sesion)
        sesion.commit()

    codigo = _en_orden(
        base_confirmada, _cancelar(vuelo.id, admin), _pagar(tipo, cliente, abierta.id)
    )

    assert codigo == error
    with base_confirmada.sesion() as sesion:
        assert sesion.get_one(Vuelo, vuelo.id).estado == "cancelado"
        assert sesion.get_one(Transaccion, abierta.id).estado == "cancelada"
        assert _ventas_abiertas(sesion, vuelo.id) == []
        assert _tiquetes_activos(sesion, vuelo.id) == 0
        assert _movimientos(sesion, cliente) == [("recarga", SALDO)]


def test_rf18_editar_espera_la_venta_en_curso_y_la_ve(base_confirmada: BaseConfirmada) -> None:
    """HU-15 · RF-18: si una compra se inicia mientras se edita el vuelo, la edición espera a que
    confirme, la ve y responde `vuelo_con_reservas`: el vuelo no cambia con una venta abierta.
    """
    with base_confirmada.sesion() as sesion:
        vuelo, cliente, admin = _escenario(sesion, "edita_despues")
    datos = VueloEntrada(
        origen="PEI",
        destino="BOG",
        fecha_salida=date(2026, 12, 5),
        hora_salida=hora(10, 0),
        precio_economica=PRECIO + 20_000,
        precio_primera=750_000,
    )

    codigo = _en_orden(
        base_confirmada,
        _iniciar("compra", cliente, vuelo),
        lambda sesion: vuelos_service.editar_vuelo(
            sesion, vuelo.id, datos, usuario_id=admin, ahora=AHORA
        ),
    )

    assert codigo == "vuelo_con_reservas"
    with base_confirmada.sesion() as sesion:
        editado = sesion.get_one(Vuelo, vuelo.id)
        assert (editado.salida, editado.precio_economica) == (SALIDA, PRECIO)
        assert _ventas_abiertas(sesion, vuelo.id) == [("compra", "pendiente")]


@pytest.mark.parametrize("tipo", ["compra", "reserva"])
def test_hu16_no_cobra_una_venta_abierta_de_un_vuelo_ya_cancelado(
    db: Session, crear_usuario: Callable[..., Any], tipo: str
) -> None:
    """HU-16 · HU-25 · HU-27: una compra pendiente o una reserva vigente que quedó abierta en un
    vuelo cancelado (datos de antes de serializar las ventas con la cancelación) no se cobra:
    responde `vuelo_no_disponible` y el saldo no cambia.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario=f"cliente_huerfana_{tipo}")
    crear_movimiento(db, cliente.id, valor=SALDO, saldo_resultante=SALDO)
    vuelo = crear_vuelo(db, salida=SALIDA)
    abierta = _iniciar(tipo, cliente.id, vuelo)(db)
    vuelo.estado = "cancelado"
    db.flush()

    with pytest.raises(service.VueloNoDisponible):
        _pagar(tipo, cliente.id, abierta.id)(db)

    assert monedero_service.saldo_de(db, cliente.id) == SALDO
    assert _movimientos(db, cliente.id) == [("recarga", SALDO)]
