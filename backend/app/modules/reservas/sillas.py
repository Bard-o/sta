"""Asignación aleatoria y agrupada de sillas (RF-41, SUP-25, SUP-26, Apéndice A del SRS).

Función pura, sin base de datos. La llaman la reserva (HU-24), la compra (HU-25), el trayecto
completo (HU-26) y, en la iteración 3, la reubicación. Trabaja con el número interno de la silla;
para mostrarla como fila y letra se usa `vuelos.service.nombre_de_silla`.

La distribución de la cabina se define aquí y no se importa de `vuelos`: `vuelos.service` ya
importa `reservas.service`, y la función no necesita nada más que el Apéndice A.
"""

import random
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from itertools import accumulate, product
from typing import Literal

from app.core.errors import Conflicto

TipoVuelo = Literal["nacional", "internacional"]
Clase = Literal["economica", "primera"]

# RF-41: k viajeros de una misma transacción y clase, 1 ≤ k ≤ 5 (máximo 5 tiquetes, HU-24).
MAXIMO_POR_CLASE = 5

# Apéndice A (SUP-25): primera silla, última silla y sillas por fila de cada clase. Las filas
# de una clase son consecutivas y, dentro de una fila, los números siguen el orden de las letras.
_DISTRIBUCION: dict[tuple[TipoVuelo, Clase], tuple[int, int, int]] = {
    ("nacional", "primera"): (1, 25, 5),  # filas 1–5, AB|CDE
    ("nacional", "economica"): (26, 150, 5),  # filas 6–30, AB|CDE
    ("internacional", "primera"): (1, 50, 5),  # filas 1–10, AB|C|DE
    ("internacional", "economica"): (51, 250, 10),  # filas 11–30, ABC|DEFG|HJK
}


class SillasInsuficientes(Conflicto):
    """RF-41: la clase no tiene sillas libres para todo el grupo; nunca se asigna una parte."""

    codigo = "clase_agotada"
    mensaje = "No quedan sillas suficientes en esta clase."


@dataclass(frozen=True)
class _Tramo:
    """Sillas libres consecutivas de una fila, entre sillas ocupadas o los bordes de la fila.

    `fila` es la posición de la fila dentro de la clase (0 es la primera fila de la clase).
    El pasillo no corta el tramo (Apéndice A: B y C en nacional son contiguas).
    """

    fila: int
    sillas: tuple[int, ...]


def asignar_sillas(
    tipo: TipoVuelo,
    clase: Clase,
    ocupadas: Collection[int],
    cantidad: int,
    rng: random.Random,
) -> list[int]:
    """Sillas para `cantidad` viajeros de una misma transacción en una clase (RF-41).

    - Paso 2: si alguna fila tiene `cantidad` sillas libres contiguas, elige uno de esos
      bloques con probabilidad uniforme entre todos los posibles (el pasillo puede quedar
      dentro).
    - Paso 3: si no, divide el grupo en el menor número posible de subbloques contiguos. Entre
      las ubicaciones con ese número se queda con las de menor dispersión (última fila menos
      primera: filas consecutivas o la misma fila) y elige una con probabilidad uniforme.
    - Paso 4: si ni siquiera hay dos sillas libres contiguas, elige sillas sueltas al azar.

    `ocupadas` son números internos de cualquier clase; los que no son de esta clase se ignoran.
    Devuelve los números internos ordenados de menor a mayor: los subbloques quedan uno tras
    otro y el viajero i de la transacción puede recibir la silla i. `rng` decide el azar; en
    producción se pasa `random.SystemRandom()` y en los tests un generador con semilla fija.

    Lanza `SillasInsuficientes` si la clase tiene menos sillas libres que viajeros, y
    `ValueError` si `cantidad` no está entre 1 y 5 o el tipo o la clase no existen.
    """
    if not 1 <= cantidad <= MAXIMO_POR_CLASE:
        raise ValueError(f"La cantidad debe estar entre 1 y {MAXIMO_POR_CLASE}: {cantidad}.")
    tramos = _tramos(_filas(tipo, clase), set(ocupadas))
    libres = [silla for tramo in tramos for silla in tramo.sillas]
    if len(libres) < cantidad:
        raise SillasInsuficientes()

    bloques = _bloques(tramos, cantidad)
    if bloques:
        return list(rng.choice(bloques))

    subbloques = _minimo_de_subbloques(tramos, cantidad)
    if subbloques < cantidad:
        return list(rng.choice(_ubicaciones_agrupadas(tramos, cantidad, subbloques)))

    return sorted(rng.sample(libres, cantidad))


def _filas(tipo: TipoVuelo, clase: Clase) -> list[range]:
    """Filas de la clase de adelante hacia atrás, cada una con sus números en orden de letra."""
    try:
        primera, ultima, por_fila = _DISTRIBUCION[(tipo, clase)]
    except KeyError:
        raise ValueError(f"No existe la clase {clase!r} en un vuelo {tipo!r}.") from None
    return [range(inicio, inicio + por_fila) for inicio in range(primera, ultima + 1, por_fila)]


def _tramos(filas: Sequence[range], ocupadas: Collection[int]) -> list[_Tramo]:
    """Tramos de sillas libres de la clase, en el orden de la cabina."""
    tramos: list[_Tramo] = []
    for indice, fila in enumerate(filas):
        actual: list[int] = []
        for silla in fila:
            if silla in ocupadas:
                if actual:
                    tramos.append(_Tramo(indice, tuple(actual)))
                actual = []
            else:
                actual.append(silla)
        if actual:
            tramos.append(_Tramo(indice, tuple(actual)))
    return tramos


def _bloques(tramos: Sequence[_Tramo], cantidad: int) -> list[tuple[int, ...]]:
    """RF-41 paso 2: todos los bloques de `cantidad` sillas libres contiguas de una fila."""
    return [
        tramo.sillas[inicio : inicio + cantidad]
        for tramo in tramos
        for inicio in range(len(tramo.sillas) - cantidad + 1)
    ]


def _minimo_de_subbloques(tramos: Sequence[_Tramo], cantidad: int) -> int:
    """Menor número de subbloques contiguos que alcanzan para el grupo (RF-41 paso 3).

    Dos subbloques nunca comparten tramo (juntos serían uno solo), así que el mínimo es el
    menor m tal que los m tramos más largos suman al menos `cantidad`. Quien llama ya comprobó
    que hay sillas libres suficientes, así que ese m existe.
    """
    largos = sorted((len(tramo.sillas) for tramo in tramos), reverse=True)
    return next(m for m, suma in enumerate(accumulate(largos), start=1) if suma >= cantidad)


def _ubicaciones_agrupadas(
    tramos: Sequence[_Tramo], cantidad: int, subbloques: int
) -> list[tuple[int, ...]]:
    """RF-41 paso 3: ubicaciones con `subbloques` subbloques y la menor dispersión de filas.

    La dispersión de una ubicación es su última fila menos la primera: 0 si todos los
    subbloques quedan en la misma fila, `subbloques - 1` si van en filas consecutivas. Se
    prueban ventanas de filas cada vez más anchas. En la primera anchura que tiene alguna
    ubicación, cada una empieza en la primera fila de su ventana (si no, cabría en una ventana
    más angosta), así que ninguna se cuenta dos veces.
    """
    por_fila: dict[int, list[_Tramo]] = {}
    for tramo in tramos:
        por_fila.setdefault(tramo.fila, []).append(tramo)
    total_filas = max(por_fila) + 1

    for dispersion in range(total_filas):
        ubicaciones: list[tuple[int, ...]] = []
        for inicio in range(total_filas - dispersion):
            ventana = [
                tramo
                for fila in range(inicio, inicio + dispersion + 1)
                for tramo in por_fila.get(fila, [])
            ]
            for combinacion in _combinaciones(ventana, subbloques, cantidad):
                ubicaciones.extend(_repartos(combinacion, cantidad))
        if ubicaciones:
            return ubicaciones
    # Con todas las filas en la ventana siempre hay ubicación: `subbloques` es alcanzable.
    raise AssertionError("No hubo ubicación con el mínimo de subbloques.")


def _combinaciones(
    ventana: Sequence[_Tramo], subbloques: int, cantidad: int
) -> Iterator[tuple[_Tramo, ...]]:
    """Grupos de `subbloques` tramos distintos de la ventana que suman al menos `cantidad`.

    Recorre los tramos del más largo al más corto y corta una rama en cuanto ni los tramos más
    largos que le quedan alcanzan; así solo visita grupos útiles aunque la ventana sea grande.
    """
    ordenados = sorted(ventana, key=lambda tramo: len(tramo.sillas), reverse=True)
    largos = [len(tramo.sillas) for tramo in ordenados]

    def explorar(
        desde: int, elegidos: tuple[_Tramo, ...], suma: int
    ) -> Iterator[tuple[_Tramo, ...]]:
        faltan = subbloques - len(elegidos)
        if faltan == 0:
            yield elegidos
            return
        for indice in range(desde, len(ordenados) - faltan + 1):
            if suma + sum(largos[indice : indice + faltan]) < cantidad:
                break  # los siguientes son más cortos: tampoco alcanzan
            yield from explorar(indice + 1, (*elegidos, ordenados[indice]), suma + largos[indice])

    yield from explorar(0, (), 0)


def _repartos(combinacion: Sequence[_Tramo], cantidad: int) -> Iterator[tuple[int, ...]]:
    """Cada forma de repartir el grupo entre los tramos (al menos una silla en cada uno) y de
    ubicar cada subbloque dentro de su tramo. Ubicaciones distintas dan sillas distintas."""
    largos = [len(tramo.sillas) for tramo in combinacion]
    for tamanos in product(*(range(1, largo + 1) for largo in largos)):
        if sum(tamanos) != cantidad:
            continue
        holguras = [
            range(largo - tamano + 1) for largo, tamano in zip(largos, tamanos, strict=True)
        ]
        for desplazamientos in product(*holguras):
            yield tuple(
                sorted(
                    silla
                    for tramo, tamano, desde in zip(
                        combinacion, tamanos, desplazamientos, strict=True
                    )
                    for silla in tramo.sillas[desde : desde + tamano]
                )
            )
