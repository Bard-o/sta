"""Catálogo estático de países y DIVIPOLA (HU-01, HU-07, HU-12).

Los archivos de `datos/` se leen una sola vez al importar el módulo; el catálogo no cambia en
ejecución. La fuente y la fecha de descarga están en `datos/README.md`.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import DatosInvalidos

_DIRECTORIO = Path(__file__).resolve().parent / "datos"

PAIS_COLOMBIA = "CO"


@dataclass(frozen=True)
class Pais:
    codigo: str
    nombre: str


@dataclass(frozen=True)
class Departamento:
    codigo: str
    nombre: str


@dataclass(frozen=True)
class Municipio:
    codigo: str
    nombre: str
    departamento: str


@dataclass(frozen=True)
class LugarResuelto:
    """Lugar de nacimiento validado y normalizado, con el texto que se guarda para mostrar."""

    pais: Pais
    municipio: Municipio | None
    ciudad: str | None
    texto: str


def _leer(nombre: str) -> object:
    return json.loads((_DIRECTORIO / nombre).read_text(encoding="utf-8"))


PAISES: tuple[Pais, ...] = tuple(
    Pais(codigo=fila["codigo"], nombre=fila["nombre"]) for fila in _leer("paises.json")
)

_divipola = _leer("divipola.json")
DEPARTAMENTOS: tuple[Departamento, ...] = tuple(
    Departamento(codigo=fila["codigo"], nombre=fila["nombre"])
    for fila in _divipola["departamentos"]
)
MUNICIPIOS: tuple[Municipio, ...] = tuple(
    Municipio(
        codigo=fila["codigo"],
        nombre=fila["nombre"],
        departamento=fila["departamento"],
    )
    for fila in _divipola["municipios"]
)

_PAISES_POR_CODIGO = {pais.codigo: pais for pais in PAISES}
_DEPARTAMENTOS_POR_CODIGO = {departamento.codigo: departamento for departamento in DEPARTAMENTOS}
_MUNICIPIOS_POR_CODIGO = {municipio.codigo: municipio for municipio in MUNICIPIOS}


def buscar_pais(codigo: str) -> Pais | None:
    return _PAISES_POR_CODIGO.get(codigo)


def buscar_departamento(codigo: str) -> Departamento | None:
    return _DEPARTAMENTOS_POR_CODIGO.get(codigo)


def buscar_municipio(codigo: str) -> Municipio | None:
    return _MUNICIPIOS_POR_CODIGO.get(codigo)


def municipios_de(departamento: str) -> list[Municipio]:
    """Municipios de un departamento, en el orden del catálogo (por nombre)."""
    return [municipio for municipio in MUNICIPIOS if municipio.departamento == departamento]


def resolver_lugar_nacimiento(
    pais: str, municipio: str | None, ciudad: str | None
) -> LugarResuelto:
    """Valida la combinación contra el catálogo y devuelve el lugar normalizado (HU-01).

    Con Colombia, el municipio es obligatorio y la ciudad va en `null`; con otro país, la ciudad
    es obligatoria y el municipio va en `null`. Lanza `DatosInvalidos` con la clave exacta del
    campo que falla.
    """
    info_pais = buscar_pais(pais)
    if info_pais is None:
        raise DatosInvalidos(campos={"lugar_nacimiento.pais": "Elige un país de la lista."})

    ciudad_limpia = ciudad.strip() if ciudad else None
    if info_pais.codigo == PAIS_COLOMBIA:
        if not municipio:
            raise DatosInvalidos(
                campos={"lugar_nacimiento.municipio": "Elige el municipio de nacimiento."}
            )
        info_municipio = buscar_municipio(municipio)
        if info_municipio is None:
            raise DatosInvalidos(
                campos={"lugar_nacimiento.municipio": "Elige un municipio de la lista."}
            )
        if ciudad_limpia:
            raise DatosInvalidos(
                campos={
                    "lugar_nacimiento.ciudad": (
                        "Si naciste en Colombia, elige el municipio y deja la ciudad vacía."
                    )
                }
            )
        departamento = _DEPARTAMENTOS_POR_CODIGO[info_municipio.departamento]
        return LugarResuelto(
            pais=info_pais,
            municipio=info_municipio,
            ciudad=None,
            texto=f"{info_municipio.nombre}, {departamento.nombre}, {info_pais.nombre}",
        )

    if municipio:
        raise DatosInvalidos(
            campos={
                "lugar_nacimiento.municipio": (
                    "El municipio solo aplica si el país de nacimiento es Colombia."
                )
            }
        )
    if not ciudad_limpia:
        raise DatosInvalidos(campos={"lugar_nacimiento.ciudad": "Escribe la ciudad de nacimiento."})
    return LugarResuelto(
        pais=info_pais,
        municipio=None,
        ciudad=ciudad_limpia,
        texto=f"{ciudad_limpia}, {info_pais.nombre}",
    )
