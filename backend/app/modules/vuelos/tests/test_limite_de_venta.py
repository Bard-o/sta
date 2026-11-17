"""Límite de venta de un vuelo (SUP-07, RF-36, RF-43)."""

from datetime import UTC, datetime, timedelta, timezone

from app.modules.vuelos import service

SALIDA = datetime(2027, 4, 15, 13, 0, tzinfo=UTC)


def test_sup07_un_vuelo_nacional_cierra_la_venta_una_hora_antes_de_salir() -> None:
    """SUP-07, RF-36: una reserva o compra en un vuelo nacional cierra 1 h antes."""
    assert service.limite_de_venta("nacional", SALIDA) == SALIDA - timedelta(hours=1)


def test_sup07_un_vuelo_internacional_cierra_la_venta_tres_horas_antes_de_salir() -> None:
    """SUP-07, RF-36: en un vuelo internacional el cierre es 3 h antes de la salida."""
    assert service.limite_de_venta("internacional", SALIDA) == SALIDA - timedelta(hours=3)


def test_rf36_el_limite_conserva_la_zona_utc_de_la_salida() -> None:
    """RF-15, RF-36: el instante sale en UTC, como la salida, para compararlo con `ahora`."""
    limite = service.limite_de_venta("nacional", SALIDA)

    assert limite.tzinfo is not None
    assert limite.utcoffset() == timedelta(0)
    assert limite == datetime(2027, 4, 15, 12, 0, tzinfo=UTC)


def test_sup07_el_limite_no_depende_de_la_zona_en_que_llegue_la_salida() -> None:
    """SUP-07: la misma salida en otra zona da el mismo instante de cierre."""
    salida_local = SALIDA.astimezone(timezone(timedelta(hours=-5)))

    assert service.limite_de_venta("internacional", salida_local) == service.limite_de_venta(
        "internacional", SALIDA
    )
