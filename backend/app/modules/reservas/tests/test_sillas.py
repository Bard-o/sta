"""Asignación aleatoria y agrupada de sillas (RF-41, SUP-25, SUP-26, Apéndice A del SRS).

Pruebas puras, sin base de datos. El azar sale de generadores con semilla fija: cada corrida
da el mismo resultado, así que las pruebas estadísticas no son intermitentes.
"""

import random
from collections import Counter
from collections.abc import Collection, Iterable
from itertools import combinations

import pytest

from app.modules.reservas.sillas import (
    Clase,
    SillasInsuficientes,
    TipoVuelo,
    asignar_sillas,
)
from app.modules.vuelos import service as vuelos_service

CLASES: list[tuple[TipoVuelo, Clase]] = [
    ("nacional", "primera"),
    ("nacional", "economica"),
    ("internacional", "primera"),
    ("internacional", "economica"),
]


def generador(semilla: int) -> random.Random:
    """Azar reproducible para los tests; en producción se pasa `random.SystemRandom()`."""
    return random.Random(semilla)


# ---------- Ayudas: la cabina vista desde vuelos (Apéndice A, SUP-25, SUP-26) ----------


def sillas_de_clase(tipo: TipoVuelo, clase: Clase) -> list[int]:
    """Números internos de la clase según la capacidad de `vuelos` (RF-13)."""
    primera, economica = vuelos_service.capacidad_de(tipo)
    if clase == "primera":
        return list(range(1, primera + 1))
    return list(range(primera + 1, primera + economica + 1))


def letras_de(tipo: TipoVuelo, clase: Clase) -> str:
    """Letras de una fila en orden, del Apéndice A."""
    return "ABCDEFGHJK" if (tipo, clase) == ("internacional", "economica") else "ABCDE"


def posicion(tipo: TipoVuelo, clase: Clase, numero: int) -> tuple[int, int]:
    """Fila y posición de la letra dentro de la fila, según `vuelos.service.nombre_de_silla`."""
    nombre = vuelos_service.nombre_de_silla(tipo, clase, numero)
    return int(nombre[:-1]), letras_de(tipo, clase).index(nombre[-1])


def subbloques(tipo: TipoVuelo, clase: Clase, sillas: Iterable[int]) -> list[list[int]]:
    """Las sillas agrupadas en tramos de una misma fila con letras consecutivas."""
    grupos: list[list[int]] = []
    anterior: tuple[int, int] | None = None
    for numero in sorted(sillas, key=lambda n: posicion(tipo, clase, n)):
        fila, letra = posicion(tipo, clase, numero)
        if anterior is not None and anterior == (fila, letra - 1):
            grupos[-1].append(numero)
        else:
            grupos.append([numero])
        anterior = (fila, letra)
    return grupos


def es_bloque(tipo: TipoVuelo, clase: Clase, sillas: Collection[int]) -> bool:
    """¿Una misma fila y letras consecutivas? El pasillo no separa (Apéndice A)."""
    return len(subbloques(tipo, clase, sillas)) == 1


def filas_de(tipo: TipoVuelo, clase: Clase, sillas: Iterable[int]) -> set[int]:
    return {posicion(tipo, clase, numero)[0] for numero in sillas}


def bloques_posibles(tipo: TipoVuelo, clase: Clase, cantidad: int) -> set[tuple[int, ...]]:
    """Todos los bloques de `cantidad` sillas contiguas de una fila en el vuelo vacío."""
    por_fila: dict[int, list[tuple[int, int]]] = {}
    for numero in sillas_de_clase(tipo, clase):
        fila, letra = posicion(tipo, clase, numero)
        por_fila.setdefault(fila, []).append((letra, numero))
    bloques: set[tuple[int, ...]] = set()
    for sillas in por_fila.values():
        ordenadas = [numero for _, numero in sorted(sillas)]
        for inicio in range(len(ordenadas) - cantidad + 1):
            bloques.add(tuple(sorted(ordenadas[inicio : inicio + cantidad])))
    return bloques


def todas_menos(tipo: TipoVuelo, clase: Clase, libres: Iterable[int]) -> set[int]:
    """Ocupadas: toda la clase salvo `libres`."""
    return set(sillas_de_clase(tipo, clase)) - set(libres)


def chi_cuadrado(
    conteos: Counter[tuple[int, ...]], categorias: Collection[tuple[int, ...]]
) -> float:
    """Estadístico χ² de bondad de ajuste contra la distribución uniforme."""
    esperado = sum(conteos.values()) / len(categorias)
    return sum((conteos[categoria] - esperado) ** 2 / esperado for categoria in categorias)


# ---------- RF-41 paso 2: un bloque contiguo elegido con probabilidad uniforme ----------


@pytest.mark.parametrize("semilla", range(20))
def test_tres_en_economica_nacional_vacia_quedan_juntas_en_una_fila(semilla: int) -> None:
    """HU-24 · RF-41: 3 viajeros en económica de un vuelo nacional vacío reciben 3 sillas
    contiguas de una misma fila."""
    sillas = asignar_sillas("nacional", "economica", set(), 3, generador(semilla))

    assert len(sillas) == 3
    assert all(26 <= numero <= 150 for numero in sillas)
    assert es_bloque("nacional", "economica", sillas)


def test_repetir_cien_veces_en_vuelos_vacios_da_bloques_distintos() -> None:
    """RF-41 · HU-24: repetir la asignación 100 veces en vuelos vacíos produce bloques en
    posiciones distintas; no siempre es la primera fila libre."""
    rng = generador(41)
    bloques = [tuple(asignar_sillas("nacional", "economica", set(), 3, rng)) for _ in range(100)]

    assert len(set(bloques)) >= 30
    assert len(filas_de("nacional", "economica", (bloque[0] for bloque in bloques))) >= 10


def test_el_bloque_se_elige_con_probabilidad_uniforme() -> None:
    """RF-41 paso 2: en el vuelo nacional vacío, los 75 bloques de 3 sillas de la económica
    salen con la misma probabilidad.

    χ² con semilla fija: el resultado es determinista. Con 74 grados de libertad el estadístico
    ronda 74 y solo supera 130 por azar con probabilidad cercana a 1 en 10.000, así que otra
    semilla también pasa; un sesgo real (preferir las primeras filas) da valores de miles.
    """
    posibles = bloques_posibles("nacional", "economica", 3)
    rng = generador(2026)
    conteos = Counter(
        tuple(asignar_sillas("nacional", "economica", set(), 3, rng))
        for _ in range(200 * len(posibles))
    )

    assert len(posibles) == 75
    assert set(conteos) == posibles
    assert chi_cuadrado(conteos, posibles) < 130


def test_la_probabilidad_es_uniforme_por_bloque_y_no_por_fila() -> None:
    """RF-41 paso 2: la fila 6 libre tiene 3 bloques de 3 y la fila 7, con 7A–7C libres, tiene
    1. Cada bloque sale cerca de 1/4 de las veces (elegir primero la fila daría 1/2 al de la
    fila 7). Ningún bloque cruza de la fila 6 a la 7. χ² con 3 grados de libertad: 21
    corresponde a una probabilidad cercana a 1 en 10.000."""
    ocupadas = todas_menos("nacional", "economica", [26, 27, 28, 29, 30, 31, 32, 33])
    posibles = {(26, 27, 28), (27, 28, 29), (28, 29, 30), (31, 32, 33)}
    rng = generador(7)
    conteos = Counter(
        tuple(asignar_sillas("nacional", "economica", ocupadas, 3, rng)) for _ in range(4000)
    )

    assert set(conteos) == posibles
    assert chi_cuadrado(conteos, posibles) < 21


@pytest.mark.parametrize(
    ("tipo", "clase", "libres", "cantidad", "esperado"),
    [
        ("nacional", "economica", [27, 28, 30], 2, [27, 28]),  # 6B|6C
        ("internacional", "primera", [2, 3, 4, 50], 3, [2, 3, 4]),  # 1B|1C|1D
        ("internacional", "economica", [53, 54, 60], 2, [53, 54]),  # 11C|11D
        ("internacional", "economica", [51, 57, 58], 2, [57, 58]),  # 11G|11H
    ],
)
def test_el_pasillo_puede_quedar_dentro_del_bloque(
    tipo: TipoVuelo, clase: Clase, libres: list[int], cantidad: int, esperado: list[int]
) -> None:
    """RF-41 paso 2 · Apéndice A: las sillas a lado y lado del pasillo son contiguas."""
    ocupadas = todas_menos(tipo, clase, libres)

    for semilla in range(10):
        assert asignar_sillas(tipo, clase, ocupadas, cantidad, generador(semilla)) == esperado


@pytest.mark.parametrize("cantidad", [1, 2, 3, 4, 5])
@pytest.mark.parametrize(("tipo", "clase"), CLASES)
def test_los_bloques_coinciden_con_la_numeracion_de_vuelos(
    tipo: TipoVuelo, clase: Clase, cantidad: int
) -> None:
    """SUP-25, SUP-26 · Apéndice A · RF-41 paso 2: en el vuelo vacío salen exactamente los
    bloques que `vuelos.service.nombre_de_silla` pone en una misma fila con letras
    consecutivas. Ninguno cruza de fila ni de clase y ninguno queda por fuera."""
    posibles = bloques_posibles(tipo, clase, cantidad)
    rng = generador(cantidad)

    vistos = {
        tuple(asignar_sillas(tipo, clase, set(), cantidad, rng)) for _ in range(30 * len(posibles))
    }

    assert vistos == posibles


def test_una_compra_en_dos_clases_recibe_un_bloque_en_cada_una() -> None:
    """RF-41 · HU-25: 2 viajeros en primera y 3 en económica reciben un bloque en cada clase
    (el algoritmo corre por separado para cada clase)."""
    for tipo in ("nacional", "internacional"):
        rng = generador(5)
        primera = asignar_sillas(tipo, "primera", set(), 2, rng)
        economica = asignar_sillas(tipo, "economica", set(primera), 3, rng)

        assert set(primera) <= set(sillas_de_clase(tipo, "primera"))
        assert set(economica) <= set(sillas_de_clase(tipo, "economica"))
        assert es_bloque(tipo, "primera", primera)
        assert es_bloque(tipo, "economica", economica)


# ---------- RF-41 paso 3: menor número de subbloques, prefiriendo filas consecutivas ----------


def test_sin_bloque_gana_el_menor_numero_de_subbloques() -> None:
    """RF-41 paso 3: sin 5 sillas contiguas, 6A–6C con 30A–30B son 2 subbloques; 6A–6C con
    dos sueltas de la fila 7 serían 3, aunque queden más cerca. Gana el menor número."""
    libres = [26, 27, 28, 31, 33, 35, 146, 147]
    ocupadas = todas_menos("nacional", "economica", libres)

    for semilla in range(10):
        sillas = asignar_sillas("nacional", "economica", ocupadas, 5, generador(semilla))
        assert sillas == [26, 27, 28, 146, 147]


def test_los_subbloques_prefieren_filas_consecutivas() -> None:
    """RF-41 paso 3: con parejas libres en las filas 6, 7, 20 y 30, un grupo de 4 queda en las
    filas 6 y 7, las únicas consecutivas."""
    libres = [26, 27, 31, 32, 96, 97, 146, 147]
    ocupadas = todas_menos("nacional", "economica", libres)

    for semilla in range(10):
        sillas = asignar_sillas("nacional", "economica", ocupadas, 4, generador(semilla))
        assert sillas == [26, 27, 31, 32]


def test_dos_subbloques_en_la_misma_fila_ganan_a_filas_consecutivas() -> None:
    """RF-41 paso 3: 15A–15B y 15D–15E (15C ocupada) están en la misma fila y ganan a las
    parejas de las filas 6 y 7; la dispersión de filas es 0."""
    libres = [26, 27, 31, 32, 71, 72, 74, 75]
    ocupadas = todas_menos("nacional", "economica", libres)

    for semilla in range(10):
        sillas = asignar_sillas("nacional", "economica", ocupadas, 4, generador(semilla))
        assert sillas == [71, 72, 74, 75]


def test_tres_subbloques_cuando_dos_no_alcanzan() -> None:
    """RF-41 paso 3: con solo 11A–11B, 12A–12B y 13A libres, un grupo de 5 va en 3 subbloques."""
    libres = [51, 52, 61, 62, 71]
    ocupadas = todas_menos("internacional", "economica", libres)

    sillas = asignar_sillas("internacional", "economica", ocupadas, 5, generador(1))

    assert sillas == libres
    assert len(subbloques("internacional", "economica", sillas)) == 3


def test_entre_ubicaciones_igual_de_buenas_se_elige_al_azar() -> None:
    """RF-41 paso 3: las filas 6–7 y 20–21 ofrecen la misma ubicación para 4 (dos parejas en
    filas consecutivas); cada una sale cerca de la mitad de las veces y ninguna otra sale."""
    libres = [26, 27, 31, 32, 96, 97, 101, 102]
    ocupadas = todas_menos("nacional", "economica", libres)
    rng = generador(3)

    conteos = Counter(
        tuple(asignar_sillas("nacional", "economica", ocupadas, 4, rng)) for _ in range(200)
    )

    assert set(conteos) == {(26, 27, 31, 32), (96, 97, 101, 102)}
    assert min(conteos.values()) >= 60


def optimas(
    tipo: TipoVuelo, clase: Clase, ocupadas: Collection[int], cantidad: int
) -> tuple[int, set[tuple[int, ...]]]:
    """Búsqueda exhaustiva de RF-41: el paso que aplica y las asignaciones que acepta.

    Recorre todos los grupos de `cantidad` sillas libres. Paso 2: los de un solo subbloque.
    Paso 3: los del menor número de subbloques y, entre ellos, la menor distancia entre la
    primera y la última fila. Paso 4 (ni dos libres contiguas): cualquier grupo.
    """
    libres = [numero for numero in sillas_de_clase(tipo, clase) if numero not in ocupadas]
    candidatas = []
    for grupo in combinations(libres, cantidad):
        filas = filas_de(tipo, clase, grupo)
        candidatas.append((len(subbloques(tipo, clase, grupo)), max(filas) - min(filas), grupo))
    minimo = min(partes for partes, _, _ in candidatas)
    if minimo == 1:
        return 2, {grupo for partes, _, grupo in candidatas if partes == 1}
    if minimo == cantidad:
        return 4, {grupo for _, _, grupo in candidatas}
    mejores = [candidata for candidata in candidatas if candidata[0] == minimo]
    dispersion = min(distancia for _, distancia, _ in mejores)
    return 3, {grupo for _, distancia, grupo in mejores if distancia == dispersion}


@pytest.mark.parametrize(("tipo", "clase"), CLASES)
def test_coincide_con_la_busqueda_exhaustiva(tipo: TipoVuelo, clase: Clase) -> None:
    """RF-41 pasos 2 a 4: en cabinas casi llenas al azar, la asignación es una de las que la
    búsqueda exhaustiva acepta: un bloque si existe; si no, el menor número de subbloques y,
    entre esos, las filas más cercanas; si no, sueltas."""
    escenarios = generador(99)
    todas = sillas_de_clase(tipo, clase)
    pasos: Counter[int] = Counter()
    for _ in range(150):
        # Libres concentradas en 25 sillas seguidas, para que salgan los tres pasos.
        inicio = escenarios.randrange(len(todas) - 24)
        libres = escenarios.sample(todas[inicio : inicio + 25], escenarios.randint(5, 12))
        cantidad = escenarios.randint(2, 5)
        ocupadas = todas_menos(tipo, clase, libres)

        sillas = asignar_sillas(tipo, clase, ocupadas, cantidad, escenarios)

        paso, aceptadas = optimas(tipo, clase, ocupadas, cantidad)
        pasos[paso] += 1
        assert tuple(sillas) in aceptadas

    assert min(pasos[paso] for paso in (2, 3, 4)) >= 10


# ---------- RF-41 paso 4: sillas sueltas al azar ----------


def test_sin_dos_sillas_contiguas_asigna_sueltas_al_azar() -> None:
    """RF-41 paso 4: con 6A, 6C, 6E, 7A, 7C y 7E libres no hay dos contiguas (6E y 7A son
    filas distintas); un grupo de 2 recibe sueltas al azar y salen todas las parejas."""
    libres = [26, 28, 30, 31, 33, 35]
    ocupadas = todas_menos("nacional", "economica", libres)
    rng = generador(11)

    vistos = {tuple(asignar_sillas("nacional", "economica", ocupadas, 2, rng)) for _ in range(600)}

    assert vistos == set(combinations(libres, 2))


# ---------- Invariantes y errores ----------


@pytest.mark.parametrize(("tipo", "clase"), CLASES)
def test_nunca_devuelve_ocupadas_de_otra_clase_ni_repetidas(tipo: TipoVuelo, clase: Clase) -> None:
    """RF-41: nunca se asigna una silla ocupada, una de otra clase ni la misma silla dos veces.
    Las ocupadas de la otra clase se ignoran y el resultado va de menor a mayor."""
    escenarios = generador(17)
    propias = sillas_de_clase(tipo, clase)
    otra: Clase = "economica" if clase == "primera" else "primera"
    for _ in range(300):
        densidad = escenarios.choice([0.0, 0.5, 0.8, 0.95])
        ocupadas = {n for n in propias if escenarios.random() < densidad}
        ocupadas |= set(escenarios.sample(sillas_de_clase(tipo, otra), 10))
        cantidad = escenarios.randint(1, 5)
        if len(propias) - len(ocupadas & set(propias)) < cantidad:
            continue

        sillas = asignar_sillas(tipo, clase, ocupadas, cantidad, escenarios)

        assert len(sillas) == len(set(sillas)) == cantidad
        assert sillas == sorted(sillas)
        assert set(sillas) <= set(propias) - ocupadas


def test_las_ocupadas_de_otra_clase_no_restan_cupo() -> None:
    """RF-41: la económica llena no impide asignar en primera, y viceversa."""
    economica = set(sillas_de_clase("nacional", "economica"))
    primera = set(sillas_de_clase("nacional", "primera"))

    assert set(asignar_sillas("nacional", "primera", economica, 5, generador(1))) <= primera
    assert set(asignar_sillas("nacional", "economica", primera, 5, generador(1))) <= economica


@pytest.mark.parametrize(("tipo", "clase"), CLASES)
def test_con_menos_libres_que_viajeros_lanza_error_sin_asignacion_parcial(
    tipo: TipoVuelo, clase: Clase
) -> None:
    """RF-41 · HU-24: con menos sillas libres que viajeros en la clase se lanza
    `SillasInsuficientes` (`clase_agotada`, 409) en lugar de una asignación parcial."""
    ocupadas = todas_menos(tipo, clase, sillas_de_clase(tipo, clase)[:2])

    with pytest.raises(SillasInsuficientes) as error:
        asignar_sillas(tipo, clase, ocupadas, 3, generador(1))

    assert error.value.codigo == "clase_agotada"
    assert error.value.status_code == 409


def test_clase_llena_lanza_error_aun_para_un_viajero() -> None:
    """RF-41: sin ninguna silla libre en la clase no se asigna nada."""
    with pytest.raises(SillasInsuficientes):
        asignar_sillas(
            "internacional", "primera", sillas_de_clase("internacional", "primera"), 1, generador(1)
        )


@pytest.mark.parametrize("cantidad", [0, 6, -1])
def test_cantidad_fuera_de_rango_es_error_de_programacion(cantidad: int) -> None:
    """RF-41: k está entre 1 y 5 (máximo 5 tiquetes por cliente y vuelo, HU-24); quien llama
    valida antes, así que otro valor es un error de programación."""
    with pytest.raises(ValueError, match="cantidad"):
        asignar_sillas("nacional", "economica", set(), cantidad, generador(1))


def test_tipo_o_clase_desconocidos_son_error_de_programacion() -> None:
    """Apéndice A: solo existen primera y económica en vuelos nacionales e internacionales."""
    with pytest.raises(ValueError, match="clase"):
        asignar_sillas("nacional", "ejecutiva", set(), 1, generador(1))


def test_misma_semilla_misma_asignacion() -> None:
    """RF-41: el azar sale solo del generador recibido; con la misma semilla se repite."""
    ocupadas = set(range(26, 120, 3))

    primera = asignar_sillas("nacional", "economica", ocupadas, 4, generador(8))
    segunda = asignar_sillas("nacional", "economica", ocupadas, 4, generador(8))

    assert primera == segunda


def test_funciona_con_el_generador_del_sistema() -> None:
    """RF-41: en producción se pasa `random.SystemRandom()`, que no admite semilla."""
    sillas = asignar_sillas("internacional", "economica", set(), 4, random.SystemRandom())

    assert es_bloque("internacional", "economica", sillas)
