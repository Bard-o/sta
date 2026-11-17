"""Comprobante de compra en PDF (RF-39 c, HU-25, HU-26, HU-27).

Función pura: recibe los datos ya consultados y devuelve los bytes del PDF, sin tocar la base
de datos. La llaman la compra (#124) y el pago de reservas (#131), que lo adjuntan al correo
del comprador con `core.mail` (#116).

Usa Helvetica, una fuente núcleo de fpdf2 que no se incrusta y cubre Windows-1252: tildes, ñ,
«», «–» y «·» salen bien. Un carácter fuera de esa codificación (un nombre en otro alfabeto) se
reduce a su letra base o a «?», para que el PDF, y con él la compra (RNF-17), nunca falle por
un nombre.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import TableBordersLayout, XPos, YPos
from fpdf.fonts import FontFace

# SUP-32: la fecha de pago se muestra en hora de Colombia, como en el resto de la interfaz.
_ZONA_NEGOCIO = "America/Bogota"
# Codificación de las fuentes núcleo de fpdf2 (WinAnsiEncoding dentro del PDF).
_CODIFICACION = "cp1252"
_FUENTE = "Helvetica"
_NOMBRE_TRAMO = ("Ida", "Regreso")  # RF-40: trayecto único (1 tramo) o completo (2)
_NOMBRE_CLASE = {"economica": "Económica", "primera": "Primera"}
_ANCHO_UTIL = 180  # A4 (210 mm) menos márgenes de 15 mm
# Grises que se leen igual impresos en blanco y negro.
_GRIS_FONDO = 235
_GRIS_TEXTO = 90


@dataclass(frozen=True)
class TramoComprobante:
    vuelo_codigo: str
    origen: str  # nombre de la ciudad
    destino: str
    salida: datetime  # UTC
    zona_origen: str  # IANA, para la hora local de salida
    llegada: datetime  # UTC
    zona_destino: str


@dataclass(frozen=True)
class TiqueteComprobante:
    tramo: int  # índice en DatosComprobante.tramos
    clase: Literal["economica", "primera"]
    silla: str  # "18C"
    precio: int  # COP


@dataclass(frozen=True)
class ViajeroComprobante:
    nombres: str
    apellidos: str
    tipo_documento: str
    numero_documento: str
    tiquetes: tuple[TiqueteComprobante, ...]


@dataclass(frozen=True)
class DatosComprobante:
    codigo: str
    comprador: str  # nombres y apellidos del cliente
    pagado_en: datetime  # UTC
    tramos: tuple[TramoComprobante, ...]
    viajeros: tuple[ViajeroComprobante, ...]  # solo los pagados en esta operación
    total: int  # lo pagado en esta operación


def generar_comprobante(datos: DatosComprobante) -> bytes:
    """PDF del comprobante de compra (RF-39 c): código, vuelos con su salida en hora local,
    viajeros con su clase y silla, valor de cada tiquete y total en COP. Español de Colombia,
    fechas dd/mm/aaaa y horas de 24 h. Función pura: no consulta la base de datos.

    Lanza ValueError si los datos no cuadran: ni uno ni dos tramos, un tiquete que apunta a un
    tramo que no existe o un total distinto de la suma de los tiquetes. Los mismos datos dan
    siempre los mismos bytes."""
    _validar(datos)
    pdf = _Pdf(datos.codigo)
    # La fecha del documento es la del pago, no la del reloj: así el PDF es determinista.
    pdf.set_creation_date(datos.pagado_en)
    pdf.set_title(f"Comprobante de compra {datos.codigo}")
    pdf.set_author("AVIANCO")
    pdf.set_creator("STA - Sistema de Tiquetes Aéreos")
    pdf.set_lang("es-CO")
    pdf.add_page()

    _encabezado(pdf)
    _resumen(pdf, datos)
    for indice, tramo in enumerate(datos.tramos):
        _tramo(pdf, datos, indice, tramo)
    _total(pdf, datos)
    return bytes(pdf.output())


def _validar(datos: DatosComprobante) -> None:
    if not 1 <= len(datos.tramos) <= len(_NOMBRE_TRAMO):
        raise ValueError("El comprobante lleva uno o dos tramos.")
    tiquetes = [tiquete for viajero in datos.viajeros for tiquete in viajero.tiquetes]
    if any(not 0 <= tiquete.tramo < len(datos.tramos) for tiquete in tiquetes):
        raise ValueError("Cada tiquete debe apuntar a un tramo del comprobante.")
    if datos.total != sum(tiquete.precio for tiquete in tiquetes):
        raise ValueError("El total debe ser la suma de los tiquetes pagados.")


class _Pdf(FPDF):
    """FPDF en A4 con pie de página y texto que nunca falla por la codificación."""

    def __init__(self, codigo: str) -> None:
        super().__init__(orientation="portrait", unit="mm", format="A4")
        self._codigo = codigo
        self.core_fonts_encoding = _CODIFICACION
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(auto=True, margin=20)

    def normalize_text(self, text: str) -> str:
        # fpdf2 pasa por aquí todo texto que escribe (celdas, tablas, pie de página).
        return super().normalize_text(_texto_imprimible(text))

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font(_FUENTE, size=8)
        self.set_text_color(_GRIS_TEXTO)
        # fpdf2 reemplaza {nb} por el total de páginas al cerrar el documento.
        pie = f"AVIANCO · Comprobante {self._codigo} · Página {self.page_no()} de {{nb}}"
        self.cell(0, 5, pie, align="C")


def _encabezado(pdf: _Pdf) -> None:
    pdf.set_text_color(0)
    pdf.set_font(_FUENTE, "B", 22)
    pdf.cell(90, 10, "AVIANCO")
    pdf.set_font(_FUENTE, "B", 14)
    pdf.cell(0, 10, "Comprobante de compra", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(_FUENTE, size=9)
    pdf.set_text_color(_GRIS_TEXTO)
    pdf.cell(0, 5, "Sistema de Tiquetes Aéreos (STA)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0)
    pdf.ln(2)
    _linea(pdf)
    pdf.ln(5)


def _resumen(pdf: _Pdf, datos: DatosComprobante) -> None:
    """Código de reserva destacado en un recuadro; al lado, comprador, pago y tipo de viaje."""
    inicio = pdf.get_y()
    pdf.set_line_width(0.4)
    pdf.rect(pdf.l_margin, inicio, 60, 24)
    pdf.set_xy(pdf.l_margin, inicio + 2)
    pdf.set_font(_FUENTE, size=9)
    pdf.cell(60, 5, "Código de reserva", align="C")
    pdf.set_xy(pdf.l_margin, inicio + 9)
    pdf.set_font(_FUENTE, "B", 24)
    pdf.cell(60, 12, datos.codigo, align="C")

    viaje = "Trayecto completo (ida y regreso)" if len(datos.tramos) == 2 else "Trayecto único"
    filas = (
        ("Comprador", datos.comprador),
        ("Pagado el", _fecha_hora(datos.pagado_en, _ZONA_NEGOCIO, "hora de Colombia")),
        ("Viaje", viaje),
    )
    y = inicio + 2
    for etiqueta, valor in filas:
        pdf.set_xy(pdf.l_margin + 66, y)
        pdf.set_font(_FUENTE, "B", 10)
        pdf.cell(24, 6, f"{etiqueta}:")
        pdf.set_font(_FUENTE, size=10)
        pdf.multi_cell(0, 6, valor, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = pdf.get_y() + 1
    pdf.set_y(max(y, inicio + 24) + 6)


def _tramo(pdf: _Pdf, datos: DatosComprobante, indice: int, tramo: TramoComprobante) -> None:
    """Vuelo, ruta, salida y llegada en hora local, y los tiquetes pagados de ese vuelo."""
    pdf.set_font(_FUENTE, "B", 12)
    titulo = (
        f"{_NOMBRE_TRAMO[indice]} · Vuelo {tramo.vuelo_codigo} · {tramo.origen} – {tramo.destino}"
    )
    pdf.multi_cell(0, 7, titulo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(_FUENTE, size=10)
    salida = _fecha_hora(tramo.salida, tramo.zona_origen, tramo.origen)
    llegada = _fecha_hora(tramo.llegada, tramo.zona_destino, tramo.destino)
    pdf.multi_cell(0, 5, f"Salida: {salida}", align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(0, 5, f"Llegada: {llegada}", align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.set_font(_FUENTE, size=9)
    with pdf.table(
        col_widths=(70, 40, 25, 15, 30),
        text_align=("LEFT", "LEFT", "LEFT", "CENTER", "RIGHT"),
        borders_layout=TableBordersLayout.HORIZONTAL_LINES,
        headings_style=FontFace(emphasis="BOLD", fill_color=_GRIS_FONDO),
        line_height=6,
    ) as tabla:
        tabla.row(("Viajero", "Documento", "Clase", "Silla", "Valor"))
        for viajero in datos.viajeros:
            for tiquete in viajero.tiquetes:
                if tiquete.tramo == indice:
                    tabla.row(
                        (
                            f"{viajero.nombres} {viajero.apellidos}",
                            f"{viajero.tipo_documento} {viajero.numero_documento}",
                            _NOMBRE_CLASE[tiquete.clase],
                            tiquete.silla,
                            _pesos(tiquete.precio),
                        )
                    )
    pdf.ln(6)


def _total(pdf: _Pdf, datos: DatosComprobante) -> None:
    _linea(pdf)
    pdf.ln(2)
    pdf.set_font(_FUENTE, "B", 13)
    pdf.cell(_ANCHO_UTIL - 50, 9, "Total pagado", align="R")
    pdf.cell(50, 9, _pesos(datos.total), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font(_FUENTE, size=9)
    pdf.set_text_color(_GRIS_TEXTO)
    pdf.multi_cell(
        0,
        5,
        "Valores en pesos colombianos (COP), pagados con el saldo del monedero. "
        "Las horas de salida y llegada están en la hora local de cada ciudad. "
        f"Cada viajero hace su check-in con el código de reserva {datos.codigo}.",
        align="L",
    )
    pdf.set_text_color(0)


def _linea(pdf: _Pdf) -> None:
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + _ANCHO_UTIL, pdf.get_y())


def _pesos(valor: int) -> str:
    """IU-06: «$ 1.250.000», con punto de miles y sin decimales."""
    return f"$ {valor:,}".replace(",", ".")


def _fecha_hora(momento: datetime, zona: str, lugar: str) -> str:
    """IU-05: «15/01/2099 14:00 Pereira (UTC-5)», en 24 h y en la hora local de `zona`."""
    local = momento.astimezone(ZoneInfo(zona))
    return f"{local:%d/%m/%Y %H:%M} {lugar} ({_desfase(local)})"


def _desfase(local: datetime) -> str:
    """«UTC-5», «UTC+2», «UTC+5:30» o «UTC», como `desfase` en frontend/src/lib/format.ts."""
    minutos = int((local.utcoffset() or timedelta()).total_seconds()) // 60
    if minutos == 0:
        return "UTC"
    horas, resto = divmod(abs(minutos), 60)
    signo = "+" if minutos > 0 else "-"
    return f"UTC{signo}{horas}" + (f":{resto:02d}" if resto else "")


def _texto_imprimible(texto: str) -> str:
    """El texto dentro de Windows-1252: lo que no cabe se reduce a su letra base («ễ» → «e»)
    o, si no la tiene, se reemplaza por «?»."""
    caracteres = []
    for caracter in unicodedata.normalize("NFC", texto):
        if _codificable(caracter):
            caracteres.append(caracter)
            continue
        base = "".join(
            parte
            for parte in unicodedata.normalize("NFKD", caracter)
            if not unicodedata.combining(parte) and _codificable(parte)
        )
        caracteres.append(base or "?")
    return "".join(caracteres)


def _codificable(caracter: str) -> bool:
    try:
        caracter.encode(_CODIFICACION)
    except UnicodeEncodeError:
        return False
    return True
