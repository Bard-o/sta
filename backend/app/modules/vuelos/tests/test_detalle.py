"""Detalle público del vuelo y precio vigente por clase (HU-19, RF-22, RF-24)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NoEncontrado
from app.modules.reservas.service import OcupacionVuelo
from app.modules.vuelos import service
from app.modules.vuelos.tests.fabricas import (
    crear_promocion_bd,
    crear_vuelo,
    simular_ocupacion,
)

# Un instante fijo antes de todos los vuelos de los tests.
AHORA = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
SALIDA = datetime(2099, 1, 15, 10, 0, tzinfo=UTC)
PRECIO_ECONOMICA = 280_000
PRECIO_PRIMERA = 750_000


# ---------- Detalle público (HU-19) ----------


def test_detalle_sin_promocion_usa_el_precio_base(db: Session) -> None:
    """HU-19 · criterio: cada clase trae su precio y su disponibilidad; sin promoción,
    `precio_vigente` es igual a `precio_base`."""
    vuelo = crear_vuelo(db, salida=SALIDA)

    detalle = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)

    assert detalle.vuelo.id == vuelo.id
    assert detalle.origen.codigo == "PEI"
    assert detalle.destino.codigo == "BOG"
    assert detalle.economica.precio_base == PRECIO_ECONOMICA
    assert detalle.economica.precio == PRECIO_ECONOMICA
    assert detalle.economica.promocion is None
    assert detalle.economica.disponibles == 125
    assert detalle.economica.agotada is False
    assert detalle.primera.precio_base == PRECIO_PRIMERA
    assert detalle.primera.precio == PRECIO_PRIMERA
    assert detalle.primera.promocion is None
    assert detalle.primera.disponibles == 25
    assert detalle.primera.agotada is False


def test_detalle_con_promocion_vigente_aplica_el_descuento_solo_a_su_clase(
    db: Session,
) -> None:
    """HU-19 · criterio: `precio_base`, `precio_vigente`, `promocion`, `disponibles` y
    `agotada` por clase; la promoción descuenta únicamente la clase a la que aplica."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    promocion = crear_promocion_bd(
        db,
        vuelo,
        porcentaje=20,
        clases=["economica"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(days=7),
    )

    detalle = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)

    assert detalle.economica.precio_base == PRECIO_ECONOMICA
    assert detalle.economica.precio == 224_000
    assert detalle.economica.promocion is not None
    assert detalle.economica.promocion.id == promocion.id
    assert detalle.economica.promocion.porcentaje == 20
    assert detalle.economica.promocion.clases == ["economica"]
    assert detalle.economica.promocion.estado == "vigente"
    assert detalle.primera.precio_base == PRECIO_PRIMERA
    assert detalle.primera.precio == PRECIO_PRIMERA
    assert detalle.primera.promocion is None


def test_detalle_con_promocion_para_las_dos_clases(db: Session) -> None:
    """HU-19 · RF-24: una promoción de ambas clases descuenta las dos."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=33,
        clases=["economica", "primera"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(days=7),
    )

    detalle = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)

    assert detalle.economica.precio == 187_600
    assert detalle.primera.precio == 502_500
    assert detalle.economica.promocion is not None
    assert detalle.primera.promocion is not None
    assert detalle.economica.promocion.clases == ["economica", "primera"]
    assert detalle.primera.promocion.clases == ["economica", "primera"]


@pytest.mark.parametrize(
    ("inicio", "fin"),
    [
        (AHORA + timedelta(days=1), AHORA + timedelta(days=3)),
        (AHORA - timedelta(days=3), AHORA - timedelta(hours=1)),
    ],
    ids=["programada", "vencida"],
)
def test_detalle_ignora_las_promociones_que_no_estan_vigentes(
    db: Session, inicio: datetime, fin: datetime
) -> None:
    """HU-19 · RF-24: una promoción programada o vencida no cambia el precio mostrado."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_promocion_bd(db, vuelo, inicio=inicio, fin=fin)

    detalle = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)

    assert detalle.economica.precio == PRECIO_ECONOMICA
    assert detalle.economica.promocion is None


def test_detalle_marca_agotada_la_clase_sin_sillas(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-19 · criterio: `disponibles` y `agotada` reflejan la ocupación real del vuelo."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_ocupacion(
        monkeypatch,
        {vuelo.id: OcupacionVuelo(vendidas_economica=120, reservadas_economica=5)},
    )

    detalle = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)

    assert detalle.economica.disponibles == 0
    assert detalle.economica.agotada is True
    assert detalle.primera.disponibles == 25
    assert detalle.primera.agotada is False


@pytest.mark.parametrize("estado", ["realizado", "cancelado"])
def test_detalle_de_un_vuelo_no_vendible_no_aplica_la_promocion(db: Session, estado: str) -> None:
    """HU-19 · criterio: responde para cualquier `estado`; si el vuelo ya se realizó o se
    canceló, la promoción pierde vigencia y se muestra el precio base."""
    vuelo = crear_vuelo(db, salida=SALIDA, estado=estado)
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=20,
        clases=["economica", "primera"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(days=7),
    )

    detalle = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)

    assert detalle.vuelo.estado == estado
    assert detalle.economica.precio == PRECIO_ECONOMICA
    assert detalle.economica.promocion is None
    assert detalle.primera.precio == PRECIO_PRIMERA
    assert detalle.primera.promocion is None


def test_detalle_de_un_vuelo_programado_que_ya_salio_no_aplica_la_promocion(
    db: Session,
) -> None:
    """HU-19 · criterio: un vuelo todavía `programado` pero con la salida pasada tampoco
    ofrece la promoción, porque ya no está disponible para la venta."""
    vuelo = crear_vuelo(db, salida=AHORA - timedelta(hours=2))
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=20,
        clases=["economica"],
        inicio=AHORA - timedelta(days=1),
        fin=AHORA + timedelta(days=1),
    )

    detalle = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)

    assert detalle.vuelo.estado == "programado"
    assert detalle.economica.precio == PRECIO_ECONOMICA
    assert detalle.economica.promocion is None


def test_detalle_usa_la_hora_inyectada_para_la_promocion(db: Session) -> None:
    """HU-19 · RF-24: la vigencia se calcula con la hora recibida, no con la del sistema."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_promocion_bd(
        db,
        vuelo,
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(hours=1),
    )

    vigente = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA)
    despues = service.obtener_vuelo_detalle(db, vuelo.id, ahora=AHORA + timedelta(hours=2))

    assert vigente.economica.promocion is not None
    assert despues.economica.promocion is None
    assert despues.economica.precio == PRECIO_ECONOMICA


def test_precio_vigente_expone_las_clases_y_el_estado(db: Session) -> None:
    """HU-19 · RF-24: el precio vigente conserva la promoción con sus clases y su estado."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_promocion_bd(
        db,
        vuelo,
        porcentaje=20,
        clases=["economica", "primera"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(days=7),
    )

    precio = service.precio_vigente(db, vuelo.id, "economica", ahora=AHORA)

    assert precio.promocion is not None
    assert precio.promocion.clases == ["economica", "primera"]
    assert precio.promocion.estado == "vigente"


def test_detalle_de_un_vuelo_inexistente_falla(db: Session) -> None:
    """HU-19: un vuelo que no existe responde con el error de negocio `NoEncontrado`."""
    with pytest.raises(NoEncontrado):
        service.obtener_vuelo_detalle(db, 999_999, ahora=AHORA)
