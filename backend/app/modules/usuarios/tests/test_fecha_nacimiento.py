"""RF-03 y SUP-43: la fecha de nacimiento no puede ser futura ni de hace más de 120 años.

Pruebas unitarias de `service.validar_fecha_nacimiento`, sin base de datos y con `hoy` fijo.
Los tests de endpoint están en test_registro.py (HU-01), test_perfil.py (HU-07) y
test_registro_administrador.py (HU-12).
"""

from datetime import date

import pytest

from app.core.errors import DatosInvalidos
from app.modules.usuarios import service

MENSAJE_FUTURA = "La fecha de nacimiento no puede ser futura."
MENSAJE_EDAD_MAXIMA = "Revisa la fecha: la edad máxima es 120 años."


def _rechazo(fecha: date, hoy: date) -> dict[str, str] | None:
    with pytest.raises(DatosInvalidos) as excinfo:
        service.validar_fecha_nacimiento(fecha, hoy)
    return excinfo.value.campos


def test_la_edad_maxima_es_120_anos():
    """RF-03 / SUP-43: el límite de edad es de 120 años."""
    assert service.EDAD_MAXIMA_ANOS == 120


@pytest.mark.parametrize(
    "fecha",
    [date(1906, 11, 3), date(2026, 11, 3), date(2024, 11, 3), date(1995, 3, 14)],
    ids=["cumple-120-hoy", "nace-hoy", "menor-de-2-anos", "adulto"],
)
def test_fechas_aceptadas(fecha: date):
    """RF-03 / SUP-43: se acepta a quien cumple exactamente 120 años hoy, a quien nace hoy
    y a los menores de edad (no hay edad mínima)."""
    service.validar_fecha_nacimiento(fecha, date(2026, 11, 3))


def test_120_anos_y_un_dia_se_rechaza():
    """RF-03 / SUP-43: quien cumplió 120 años ayer ya supera la edad máxima."""
    campos = _rechazo(date(1906, 11, 2), date(2026, 11, 3))

    assert campos == {"fecha_nacimiento": MENSAJE_EDAD_MAXIMA}


def test_fecha_futura_se_rechaza():
    """RF-03: una fecha de nacimiento posterior a hoy se rechaza con el mensaje de fecha futura."""
    campos = _rechazo(date(2026, 11, 4), date(2026, 11, 3))

    assert campos == {"fecha_nacimiento": MENSAJE_FUTURA}


def test_29_de_febrero_en_ano_bisiesto():
    """SUP-43: con hoy = 29/02/2024 (1904 fue bisiesto) se acepta el 29/02/1904, no el 28/02."""
    hoy = date(2024, 2, 29)

    service.validar_fecha_nacimiento(date(1904, 2, 29), hoy)
    assert _rechazo(date(1904, 2, 28), hoy) == {"fecha_nacimiento": MENSAJE_EDAD_MAXIMA}


@pytest.mark.parametrize(
    ("hoy", "fecha", "aceptada"),
    [
        (date(2100, 2, 28), date(1980, 2, 29), True),
        (date(2100, 2, 28), date(1980, 2, 27), False),
        (date(2100, 3, 1), date(1980, 2, 29), False),
        (date(2100, 3, 1), date(1980, 3, 1), True),
    ],
    ids=["29-feb-cumple-el-28", "27-feb-ya-paso", "29-feb-cumplio-ayer", "1-mar-cumple-hoy"],
)
def test_29_de_febrero_contra_ano_no_bisiesto(hoy: date, fecha: date, aceptada: bool):
    """SUP-43: en 2100 (no bisiesto) quien nació un 29 de febrero cumple años el 28 de febrero."""
    if aceptada:
        service.validar_fecha_nacimiento(fecha, hoy)
    else:
        assert _rechazo(fecha, hoy) == {"fecha_nacimiento": MENSAJE_EDAD_MAXIMA}


def test_hoy_29_de_febrero_con_ano_de_hace_120_no_bisiesto():
    """SUP-43: con hoy = 29/02/2020 (1900 no fue bisiesto) quien nació el 28/02/1900 cumplió
    120 años ayer; la fecha mínima aceptada es el 01/03/1900."""
    hoy = date(2020, 2, 29)

    assert _rechazo(date(1900, 2, 28), hoy) == {"fecha_nacimiento": MENSAJE_EDAD_MAXIMA}
    service.validar_fecha_nacimiento(date(1900, 3, 1), hoy)
