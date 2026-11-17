"""Comprobante de compra en PDF (RF-39 c, HU-25, HU-26, HU-27, IU-05, IU-06, IU-08).

Pruebas puras, sin base de datos: arman los datos con `datos_comprobante`, generan el PDF y
leen su texto con pypdf. pypdf parte el texto en líneas y celdas, así que se compara con los
espacios normalizados.
"""

import io
import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal

import pytest
from pypdf import PdfReader

from app.modules.reservas.comprobante import (
    DatosComprobante,
    TiqueteComprobante,
    TramoComprobante,
    ViajeroComprobante,
    generar_comprobante,
)

CODIGO = "K7Q2MX"
PAGADO_EN = datetime(2099, 1, 10, 14, 30, tzinfo=UTC)  # 09:30 en Colombia (UTC-5)

# Pereira → Nueva York en enero: las dos ciudades en UTC-5.
IDA = TramoComprobante(
    vuelo_codigo="AV1234",
    origen="Pereira",
    destino="Nueva York",
    salida=datetime(2099, 1, 15, 19, 0, tzinfo=UTC),  # 14:00 en Pereira
    zona_origen="America/Bogota",
    llegada=datetime(2099, 1, 16, 0, 20, tzinfo=UTC),  # 19:20 del 15/01 en Nueva York
    zona_destino="America/New_York",
)
# Nueva York → Cartagena en julio: Nueva York en horario de verano (UTC-4).
REGRESO = TramoComprobante(
    vuelo_codigo="AV5678",
    origen="Nueva York",
    destino="Cartagena",
    salida=datetime(2099, 7, 20, 23, 45, tzinfo=UTC),  # 19:45 en Nueva York
    zona_origen="America/New_York",
    llegada=datetime(2099, 7, 21, 4, 30, tzinfo=UTC),  # 23:30 del 20/07 en Cartagena
    zona_destino="America/Bogota",
)


def tiquete(
    silla: str = "12C",
    *,
    tramo: int = 0,
    clase: Literal["economica", "primera"] = "economica",
    precio: int = 1_250_000,
) -> TiqueteComprobante:
    return TiqueteComprobante(tramo=tramo, clase=clase, silla=silla, precio=precio)


def viajero(
    nombres: str = "Ana María",
    apellidos: str = "Pérez Gómez",
    *,
    tipo_documento: str = "CC",
    numero_documento: str = "1234567",
    tiquetes: tuple[TiqueteComprobante, ...] | None = None,
) -> ViajeroComprobante:
    return ViajeroComprobante(
        nombres=nombres,
        apellidos=apellidos,
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
        tiquetes=tiquetes if tiquetes is not None else (tiquete(),),
    )


def datos_comprobante(
    *,
    tramos: tuple[TramoComprobante, ...] = (IDA,),
    viajeros: tuple[ViajeroComprobante, ...] | None = None,
    total: int | None = None,
) -> DatosComprobante:
    """Datos válidos de una compra; el total es la suma de los tiquetes si no se da."""
    viajeros = viajeros if viajeros is not None else (viajero(),)
    if total is None:
        total = sum(t.precio for v in viajeros for t in v.tiquetes)
    return DatosComprobante(
        codigo=CODIGO,
        comprador="Ana María Pérez Gómez",
        pagado_en=PAGADO_EN,
        tramos=tramos,
        viajeros=viajeros,
        total=total,
    )


def texto_del_pdf(contenido: bytes) -> str:
    """Texto de todas las páginas, con los espacios y saltos de línea normalizados."""
    lector = PdfReader(io.BytesIO(contenido))
    return " ".join(" ".join(pagina.extract_text() for pagina in lector.pages).split())


def test_trae_el_codigo_y_cada_vuelo_con_su_ruta_y_su_salida_en_hora_local() -> None:
    """Criterio 1 · RF-39 (c) · HU-25 · IU-05: el código de reserva y el vuelo con su ruta,
    su salida en la hora local del origen y su llegada en la del destino."""
    texto = texto_del_pdf(generar_comprobante(datos_comprobante()))

    assert "Código de reserva K7Q2MX" in texto
    assert "Trayecto único" in texto
    assert "Ida · Vuelo AV1234 · Pereira – Nueva York" in texto
    assert "Salida: 15/01/2099 14:00 Pereira (UTC-5)" in texto
    assert "Llegada: 15/01/2099 19:20 Nueva York (UTC-5)" in texto
    assert "Regreso" not in texto


def test_cada_viajero_lleva_su_clase_su_silla_y_el_valor_de_su_tiquete() -> None:
    """Criterio 1 · RF-39 (c) · HU-25: cada viajero en su fila, con documento, clase, silla
    (`12C`) y valor del tiquete en COP con punto de miles."""
    datos = datos_comprobante(
        viajeros=(
            viajero(tiquetes=(tiquete("3A", clase="primera", precio=3_200_000),)),
            viajero(
                "Juan Pablo",
                "Ríos",
                tipo_documento="TI",
                numero_documento="1098765",
                tiquetes=(tiquete("12C"),),
            ),
        )
    )
    texto = texto_del_pdf(generar_comprobante(datos))

    assert "Viajero Documento Clase Silla Valor" in texto
    assert "Ana María Pérez Gómez CC 1234567 Primera 3A $ 3.200.000" in texto
    assert "Juan Pablo Ríos TI 1098765 Económica 12C $ 1.250.000" in texto


def test_el_total_va_en_cop_con_punto_de_miles_y_sin_decimales() -> None:
    """Criterio 1 · RF-39 (c) · IU-06: «$ 12.500.000», nunca «12,500,000» ni «12500000.00»."""
    datos = datos_comprobante(
        viajeros=(
            viajero(tiquetes=(tiquete("1A", clase="primera", precio=10_000_000),)),
            viajero("Juan Pablo", "Ríos", tiquetes=(tiquete("12C", precio=2_500_000),)),
        )
    )
    texto = texto_del_pdf(generar_comprobante(datos))

    assert "Total pagado $ 12.500.000" in texto
    assert "$ 10.000.000" in texto
    assert "$ 2.500.000" in texto
    assert "12,500,000" not in texto
    assert "12500000" not in texto


def test_un_trayecto_completo_muestra_los_dos_tramos_bajo_el_mismo_codigo() -> None:
    """Criterio 2 · HU-26: Pereira → Nueva York en primera y Nueva York → Cartagena en
    económica, en un solo comprobante con un solo código y el total de los dos tramos."""
    datos = datos_comprobante(
        tramos=(IDA, REGRESO),
        viajeros=(
            viajero(
                tiquetes=(
                    tiquete("2A", tramo=0, clase="primera", precio=3_200_000),
                    tiquete("12C", tramo=1, clase="economica", precio=1_250_000),
                )
            ),
        ),
    )
    texto = texto_del_pdf(generar_comprobante(datos))

    assert "Código de reserva K7Q2MX" in texto
    assert "Trayecto completo (ida y regreso)" in texto
    ida = texto.index("Ida · Vuelo AV1234 · Pereira – Nueva York")
    regreso = texto.index("Regreso · Vuelo AV5678 · Nueva York – Cartagena")
    assert ida < regreso
    # Cada tiquete aparece bajo su tramo, con la clase elegida en ese tramo.
    primera = texto.index("Ana María Pérez Gómez CC 1234567 Primera 2A $ 3.200.000")
    economica = texto.index("Ana María Pérez Gómez CC 1234567 Económica 12C $ 1.250.000")
    assert ida < primera < regreso < economica
    assert "Total pagado $ 4.450.000" in texto


def test_textos_en_espanol_con_fechas_dd_mm_aaaa_y_horas_de_24_h() -> None:
    """Criterio 3 · IU-05 · IU-08: etiquetas en español, fechas dd/mm/aaaa (día 20 primero) y
    horas de 24 h en la zona de cada ciudad, con su desfase; nada de AM/PM ni fechas ISO."""
    datos = datos_comprobante(
        tramos=(IDA, REGRESO),
        viajeros=(
            viajero(
                tiquetes=(
                    tiquete("2A", tramo=0, clase="primera", precio=3_200_000),
                    tiquete("12C", tramo=1),
                )
            ),
        ),
    )
    texto = texto_del_pdf(generar_comprobante(datos))

    for etiqueta in (
        "Comprobante de compra",
        "Sistema de Tiquetes Aéreos (STA)",
        "Código de reserva",
        "Comprador: Ana María Pérez Gómez",
        "Valores en pesos colombianos (COP)",
        "Página 1 de 1",
    ):
        assert etiqueta in texto
    # Pago en hora de Colombia (SUP-32): 14:30 UTC son las 09:30.
    assert "Pagado el: 10/01/2099 09:30 hora de Colombia (UTC-5)" in texto
    # 23:45 UTC en julio son las 19:45 en Nueva York (UTC-4, horario de verano) y la llegada,
    # el 21/07 en UTC, sigue siendo el 20/07 en Cartagena.
    assert "Salida: 20/07/2099 19:45 Nueva York (UTC-4)" in texto
    assert "Llegada: 20/07/2099 23:30 Cartagena (UTC-5)" in texto
    assert re.search(r"\b(AM|PM)\b|\b[ap]\. ?m\.", texto) is None
    assert re.search(r"\d{4}-\d{2}-\d{2}", texto) is None


@pytest.mark.parametrize(
    ("ciudad", "zona", "mes", "esperado"),
    [
        ("Madrid", "Europe/Madrid", 1, "15/01/2099 13:00 Madrid (UTC+1)"),
        ("Madrid", "Europe/Madrid", 7, "15/07/2099 14:00 Madrid (UTC+2)"),
        ("Londres", "Europe/London", 1, "15/01/2099 12:00 Londres (UTC)"),
        ("Bombay", "Asia/Kolkata", 1, "15/01/2099 17:30 Bombay (UTC+5:30)"),
    ],
)
def test_la_salida_lleva_la_ciudad_y_el_desfase_de_su_zona(
    ciudad: str, zona: str, mes: int, esperado: str
) -> None:
    """IU-05: «15:00 Madrid (UTC+2)». El desfase sale de la zona IANA en la fecha del vuelo,
    con horario de verano y medias horas, como `desfase` del frontend. Salida a las 12:00 UTC."""
    salida = datetime(2099, mes, 15, 12, 0, tzinfo=UTC)
    tramo = replace(IDA, origen=ciudad, zona_origen=zona, salida=salida)
    texto = texto_del_pdf(generar_comprobante(datos_comprobante(tramos=(tramo,))))

    assert f"Salida: {esperado}" in texto


def test_el_pago_de_una_reserva_muestra_solo_los_viajeros_pagados() -> None:
    """HU-27: al pagar 2 de 4 viajeros, el comprobante trae esos 2 y el total de esta
    operación (quien llama pasa solo los pagados)."""
    pagados = (
        viajero(tiquetes=(tiquete("12C"),)),
        viajero("Juan Pablo", "Ríos", numero_documento="7654321", tiquetes=(tiquete("12D"),)),
    )
    texto = texto_del_pdf(generar_comprobante(datos_comprobante(viajeros=pagados)))

    assert "Ana María Pérez Gómez CC 1234567 Económica 12C $ 1.250.000" in texto
    assert "Juan Pablo Ríos CC 7654321 Económica 12D $ 1.250.000" in texto
    assert texto.count("Económica") == 2
    assert "Total pagado $ 2.500.000" in texto


def test_un_nombre_fuera_de_la_fuente_no_rompe_el_comprobante() -> None:
    """RF-39 (c) · RNF-17: el PDF se genera aunque un nombre traiga letras que Helvetica no
    tiene; tildes y ñ se conservan, las letras con diacríticos raros pierden el diacrítico y
    los caracteres sin equivalente salen como «?». Si fallara, se revertiría la compra."""
    datos = datos_comprobante(
        viajeros=(
            viajero("José Ñañez", "Müller"),
            viajero(
                "Nguyễn Văn",
                "李",
                tipo_documento="PA",
                numero_documento="AB12345",
                tiquetes=(tiquete("12D"),),
            ),
        )
    )
    texto = texto_del_pdf(generar_comprobante(datos))

    assert "José Ñañez Müller CC 1234567" in texto
    assert "Nguyen Van ? PA AB12345" in texto


def test_los_mismos_datos_dan_el_mismo_pdf() -> None:
    """RF-39 (c): función pura; la fecha del documento es la del pago, no la del reloj."""
    datos = datos_comprobante()
    contenido = generar_comprobante(datos)

    assert contenido.startswith(b"%PDF-")
    assert generar_comprobante(datos) == contenido
    metadatos = PdfReader(io.BytesIO(contenido)).metadata
    assert metadatos is not None
    assert metadatos.title == "Comprobante de compra K7Q2MX"
    assert metadatos.creation_date == PAGADO_EN


@pytest.mark.parametrize(
    ("datos", "mensaje"),
    [
        (datos_comprobante(tramos=()), "uno o dos tramos"),
        (datos_comprobante(tramos=(IDA, REGRESO, IDA)), "uno o dos tramos"),
        (
            datos_comprobante(viajeros=(viajero(tiquetes=(tiquete(tramo=1),)),)),
            "tramo del comprobante",
        ),
        (datos_comprobante(total=1), "suma de los tiquetes"),
    ],
    ids=["sin-tramos", "tres-tramos", "tiquete-sin-tramo", "total-distinto"],
)
def test_datos_que_no_cuadran_lanzan_value_error(datos: DatosComprobante, mensaje: str) -> None:
    """RF-39 (c): un error de quien llama no se convierte en un comprobante engañoso."""
    with pytest.raises(ValueError, match=mensaje):
        generar_comprobante(datos)
