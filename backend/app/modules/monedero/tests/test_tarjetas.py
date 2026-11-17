"""Validación de las tarjetas simuladas (HU-28, RF-46, RNF-12)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.monedero import service
from app.modules.monedero.schemas import TarjetaEntrada

AHORA = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
NUMERO_VISA = "4242424242424242"


def _entrada(**cambios: str) -> TarjetaEntrada:
    datos = {
        "tipo": "credito",
        "titular": "LAURA GOMEZ RIOS",
        "numero": NUMERO_VISA,
        "vencimiento": "08/28",
        "cvv": "123",
    }
    datos.update(cambios)
    return TarjetaEntrada(**datos)


def test_hu28_rechaza_un_numero_que_no_pasa_luhn() -> None:
    """HU-28, RF-46: un número que no pasa Luhn se rechaza en `campos.numero`."""
    assert not service.luhn_valido("4242424242424241")

    with pytest.raises(service.TarjetaInvalida) as exc:
        service.validar_tarjeta("4242424242424241", "08/28", ahora=AHORA)

    assert exc.value.status_code == 422
    assert exc.value.codigo == "tarjeta_invalida"
    assert exc.value.campos == {"numero": "El número no es válido. Revisa los dígitos."}


def test_hu28_rechaza_una_tarjeta_vencida() -> None:
    """HU-28, RF-46: un vencimiento anterior al mes actual se rechaza."""
    with pytest.raises(service.TarjetaVencida) as exc:
        service.validar_tarjeta(NUMERO_VISA, "05/26", ahora=AHORA)

    assert exc.value.status_code == 422
    assert exc.value.codigo == "tarjeta_vencida"
    assert exc.value.campos == {"vencimiento": "La tarjeta está vencida."}


def test_hu28_la_tarjeta_sirve_hasta_el_ultimo_dia_de_su_mes() -> None:
    """HU-28: el mes de vencimiento en curso todavía es válido."""
    assert not service.tarjeta_vencida("11/26", ahora=AHORA)
    assert service.tarjeta_vencida("10/26", ahora=AHORA)


def test_hu28_acepta_un_numero_valido() -> None:
    """HU-28, RF-46: un número válido pasa y devuelve la franquicia."""
    assert service.luhn_valido(NUMERO_VISA)
    assert service.validar_tarjeta(NUMERO_VISA, "08/28", ahora=AHORA) == "visa"


@pytest.mark.parametrize(
    ("numero", "franquicia"),
    [
        ("4242424242424242", "visa"),
        ("5555555555554444", "mastercard"),
        ("2221000000000009", "mastercard"),
        ("378282246310005", "amex"),
        ("30569309025904", "diners"),
        ("6011111111111117", "otra"),
    ],
)
def test_hu28_deduce_la_franquicia_del_numero(numero: str, franquicia: str) -> None:
    """HU-28: Visa, Mastercard, Amex, Diners y «otra» salen del número."""
    assert service.luhn_valido(numero)
    assert service.franquicia_de(numero) == franquicia


def test_hu28_el_formato_del_cvv_lo_valida_el_schema() -> None:
    """HU-28, RNF-12: el CVV se valida (3 o 4 dígitos) y nunca llega al service."""
    assert _entrada(cvv="123").cvv == "123"
    assert _entrada(cvv="1234").cvv == "1234"

    with pytest.raises(ValidationError):
        _entrada(cvv="12345")
    with pytest.raises(ValidationError):
        _entrada(cvv="abc")
