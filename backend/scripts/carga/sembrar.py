"""Crea y siembra la base `sta_carga` para la prueba de carga de la búsqueda (RNF-01, #135).

Uso, desde la raíz del repositorio (todo corre en el contenedor):

    docker compose --profile carga run --rm backend-carga uv run python -m scripts.carga.sembrar
    docker compose --profile carga run --rm backend-carga \
        uv run python -m scripts.carga.sembrar --limpiar

Cada corrida borra y recrea la base `*_carga` de `DATABASE_URL`, la migra a `head` y la llena con
vuelos, promociones y clientes sintéticos. La base de desarrollo nunca se toca: el script se
niega a seguir si `DATABASE_URL` no apunta a una base cuyo nombre termine en `_carga`.

Los datos salen de un generador con semilla: la misma semilla da los mismos conteos. Se escribe
con tablas reflejadas y `insert()` de Core (no se importan los `models.py` de otros módulos) y
así la base valida sus CHECK y sus únicos y aplica sus valores por defecto, como el código
`STA-xxxxx` del vuelo.
"""

import argparse
import os
import random
import re
import time as reloj
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, insert, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.core.errors import DatosInvalidos
from app.core.security import hash_contrasena
from app.modules.vuelos import service as vuelos_service

CONTRASENA = os.environ.get("CARGA_CONTRASENA", "CargaSta2026")
PREFIJO_CLIENTE = "carga_cliente_"
MAXIMO_VUELOS = 99_999  # el código STA-xxxxx tiene cinco dígitos
TAMANO_LOTE = 2_000
REINTENTOS_DE_SALIDA = 20
ZONA_BOGOTA = ZoneInfo("America/Bogota")

# Peso de cada ciudad al elegir rutas: los hubs concentran los vuelos. Peso de la ruta = producto.
PESO_CIUDAD = {
    "BOG": 10,
    "MDE": 6,
    "CLO": 5,
    "CTG": 5,
    "BAQ": 4,
    "PEI": 4,
    "BGA": 3,
    "SMR": 3,
    "ADZ": 3,
    "CUC": 2,
    "MIA": 5,
    "JFK": 4,
    "MAD": 4,
    "EZE": 2,
    "LHR": 2,
}
# Horas locales de salida del origen (05:00 a 22:55): picos de mañana (6 a 9) y de tarde (16 a 20).
PESO_POR_HORA = {
    5: 2,
    **dict.fromkeys(range(6, 10), 6),
    **dict.fromkeys(range(10, 16), 4),
    **dict.fromkeys(range(16, 21), 6),
    21: 3,
    22: 1,
}
HORAS = list(PESO_POR_HORA)
PESO_HORA = list(PESO_POR_HORA.values())
PORCENTAJES_PROMOCION = [10, 15, 20, 25, 30, 40, 50]


@dataclass(frozen=True)
class Ruta:
    origen: str
    destino: str
    zona_origen: str
    tipo: str
    duracion: int
    capacidad_primera: int
    capacidad_economica: int
    peso: int


def _nombre_de_base_de_carga(url_base: str) -> str:
    """Nombre de la base de carga; aborta si no es `*_carga` o es la de desarrollo."""
    nombre = make_url(url_base).database or ""
    if not re.fullmatch(r"[a-z0-9_]+_carga", nombre) or nombre == os.environ.get("POSTGRES_DB"):
        raise SystemExit(
            f"DATABASE_URL apunta a «{nombre}»: debe ser una base *_carga distinta de la de "
            "desarrollo."
        )
    return nombre


def _redondear(valor: float) -> int:
    """Precios en miles de pesos, como los de un catálogo (mínimo 1.000)."""
    return max(1_000, round(valor / 1_000) * 1_000)


def _recrear_base(url_servidor: Any, nombre: str, *, crear: bool) -> None:
    """Borra la base de carga (expulsando a quien esté conectado) y, si `crear`, la crea vacía."""
    motor = create_engine(url_servidor, isolation_level="AUTOCOMMIT")
    try:
        with motor.connect() as conexion:
            conexion.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
            if crear:
                conexion.execute(text(f'CREATE DATABASE "{nombre}"'))
    finally:
        motor.dispose()


def _migrar(url_base: str) -> None:
    configuracion = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    configuracion.attributes["url"] = url_base
    command.upgrade(configuracion, "head")


def _rutas_validas(db: Session) -> list[Ruta]:
    """Todos los pares de ciudades que RF-14 permite, con su duración y sus capacidades."""
    ciudades = vuelos_service.listar_ciudades(db)
    rutas: list[Ruta] = []
    for origen in ciudades:
        for destino in ciudades:
            if origen.codigo == destino.codigo:
                continue
            try:
                tipo = vuelos_service.validar_ruta(origen, destino)
            except DatosInvalidos:
                continue  # RutaNoPermitida también es DatosInvalidos: esa ruta no existe
            primera, economica = vuelos_service.capacidad_de(tipo)
            rutas.append(
                Ruta(
                    origen=origen.codigo,
                    destino=destino.codigo,
                    zona_origen=origen.zona_horaria,
                    tipo=tipo,
                    duracion=vuelos_service.calcular_duracion_minutos(origen, destino),
                    capacidad_primera=primera,
                    capacidad_economica=economica,
                    peso=PESO_CIUDAD.get(origen.codigo, 1) * PESO_CIUDAD.get(destino.codigo, 1),
                )
            )
    return rutas


def _precios(rng: random.Random, ruta: Ruta) -> tuple[int, int]:
    """Precio de económica y de primera de un vuelo, creciente con la duración."""
    if ruta.tipo == "nacional":
        economica = _redondear(rng.uniform(0.8, 1.3) * (110_000 + 2_600 * ruta.duracion))
        primera = _redondear(economica * rng.uniform(2.2, 2.9))
    else:
        economica = _redondear(rng.uniform(0.85, 1.25) * (700_000 + 3_200 * ruta.duracion))
        primera = _redondear(economica * rng.uniform(2.5, 3.2))
    return economica, primera


def _salida(rng: random.Random, ruta: Ruta, dia: date) -> datetime:
    """Salida en UTC a una hora local del origen con la distribución de HORAS."""
    hora = rng.choices(HORAS, weights=PESO_HORA)[0]
    minuto = rng.randrange(0, 60, 5)
    return vuelos_service.salida_en_utc(dia, time(hora, minuto), ruta.zona_origen)


def _fila_de_vuelo(rng: random.Random, ruta: Ruta, salida: datetime, estado: str) -> dict[str, Any]:
    economica, primera = _precios(rng, ruta)
    return {
        "tipo": ruta.tipo,
        "origen_codigo": ruta.origen,
        "destino_codigo": ruta.destino,
        "salida": salida,
        "llegada": salida + timedelta(minutes=ruta.duracion),
        "duracion_minutos": ruta.duracion,
        "precio_economica": economica,
        "precio_primera": primera,
        "capacidad_primera": ruta.capacidad_primera,
        "capacidad_economica": ruta.capacidad_economica,
        "estado": estado,
    }


def _elegir_rutas(rng: random.Random, rutas: Sequence[Ruta], cantidad: int) -> list[Ruta]:
    """80 % de vuelos nacionales y 20 % internacionales, con rutas elegidas por peso."""
    nacionales = [ruta for ruta in rutas if ruta.tipo == "nacional"]
    internacionales = [ruta for ruta in rutas if ruta.tipo == "internacional"]
    n_nacionales = round(cantidad * 0.8)
    elegidas = rng.choices(nacionales, weights=[r.peso for r in nacionales], k=n_nacionales)
    elegidas += rng.choices(
        internacionales,
        weights=[r.peso for r in internacionales],
        k=cantidad - n_nacionales,
    )
    rng.shuffle(elegidas)
    return elegidas


def _vuelos_programados(
    rng: random.Random, rutas: Sequence[Ruta], cantidad: int, hoy: date, dias: int
) -> list[dict[str, Any]]:
    """Vuelos de hoy+2 a hoy+dias+1 (hora de Bogotá), sin repetir (origen, destino, salida)."""
    usadas: set[tuple[str, str, datetime]] = set()
    filas: list[dict[str, Any]] = []
    for ruta in _elegir_rutas(rng, rutas, cantidad):
        for _ in range(REINTENTOS_DE_SALIDA):
            salida = _salida(rng, ruta, hoy + timedelta(days=rng.randint(2, dias + 1)))
            clave = (ruta.origen, ruta.destino, salida)
            if clave not in usadas:
                usadas.add(clave)
                filas.append(_fila_de_vuelo(rng, ruta, salida, "programado"))
                break
    return filas


def _vuelos_con_estado(
    rng: random.Random,
    rutas: Sequence[Ruta],
    cantidad: int,
    hoy: date,
    estado: str,
    dias: tuple[int, int],
) -> list[dict[str, Any]]:
    """Vuelos realizados (días negativos) o cancelados (días futuros): no compiten con el único
    parcial de los programados, pero tampoco se repiten entre sí."""
    usadas: set[tuple[str, str, datetime]] = set()
    filas: list[dict[str, Any]] = []
    for ruta in _elegir_rutas(rng, rutas, cantidad):
        for _ in range(REINTENTOS_DE_SALIDA):
            salida = _salida(rng, ruta, hoy + timedelta(days=rng.randint(*dias)))
            clave = (ruta.origen, ruta.destino, salida)
            if clave not in usadas:
                usadas.add(clave)
                filas.append(_fila_de_vuelo(rng, ruta, salida, estado))
                break
    return filas


def _insertar(motor: Engine, tabla: Table, filas: Sequence[dict[str, Any]]) -> None:
    """Inserta en lotes dentro de una sola transacción."""
    with motor.begin() as conexion:
        for inicio in range(0, len(filas), TAMANO_LOTE):
            conexion.execute(insert(tabla), list(filas[inicio : inicio + TAMANO_LOTE]))


def _promociones(
    rng: random.Random,
    programados: Sequence[tuple[int, datetime]],
    fraccion: float,
    ahora: datetime,
) -> list[dict[str, Any]]:
    """Una promoción como mucho por vuelo; casi todas vigentes y cerca del 1 % por empezar."""
    filas: list[dict[str, Any]] = []
    elegidos = rng.sample(list(programados), round(len(programados) * fraccion))
    for vuelo_id, salida in elegidos:
        sorteo = rng.random()
        solo_primera = 0.70 <= sorteo < 0.85
        ambas = sorteo >= 0.85
        porcentaje = rng.choice(PORCENTAJES_PROMOCION)
        futura = rng.random() < 0.01
        if futura:
            inicio = ahora + timedelta(hours=rng.randint(1, 48))
            fin = min(inicio + timedelta(days=rng.randint(3, 45)), salida - timedelta(hours=1))
        else:
            inicio = ahora - timedelta(hours=rng.randint(1, 120))
            fin = min(ahora + timedelta(days=rng.randint(3, 45)), salida - timedelta(hours=1))
        if fin <= max(ahora, inicio):
            continue
        filas.append(
            {
                "vuelo_id": vuelo_id,
                "porcentaje": porcentaje,
                "aplica_economica": not solo_primera,
                "aplica_primera": solo_primera or ambas,
                "inicio": inicio,
                "fin": fin,
                "estado": "programada",
                "creada_en": ahora,
            }
        )
    return filas


def _clientes(cantidad: int, hash_unico: str, ahora: datetime) -> list[dict[str, Any]]:
    """Clientes verificados con la misma contraseña (se calcula un solo hash)."""
    return [
        {
            "nombre_usuario": f"{PREFIJO_CLIENTE}{n:03d}",
            "email": f"{PREFIJO_CLIENTE}{n:03d}@avianco.test",
            "password_hash": hash_unico,
            "rol": "cliente",
            "email_verificado": True,
            "tipo_documento": "CC",
            "numero_documento": f"9{n:08d}",
            "nombres": f"Cliente {n:03d}",
            "apellidos": "De Carga",
            "fecha_nacimiento": date(1990, 1, 1),
            "fecha_aceptacion_politica": ahora,
        }
        for n in range(1, cantidad + 1)
    ]


def _resumen(motor: Engine, args: argparse.Namespace, segundos: float) -> None:
    ahora = datetime.now(UTC)
    with motor.connect() as conexion:

        def valor(sql: str, **parametros: Any) -> Any:
            return conexion.execute(text(sql), parametros).scalar_one()

        por_estado = conexion.execute(
            text("SELECT estado, tipo, count(*) FROM vuelos GROUP BY 1, 2 ORDER BY 1, 2")
        ).all()
        rutas_con_vuelos = valor(
            "SELECT count(DISTINCT (origen_codigo, destino_codigo)) FROM vuelos"
            " WHERE estado = 'programado'"
        )
        primera, ultima = conexion.execute(
            text("SELECT min(salida), max(salida) FROM vuelos WHERE estado = 'programado'")
        ).one()
        promociones = valor("SELECT count(*) FROM promociones")
        vigentes = valor(
            "SELECT count(*) FROM promociones"
            " WHERE estado = 'programada' AND inicio <= :ahora AND fin > :ahora",
            ahora=ahora,
        )
        futuras = valor("SELECT count(*) FROM promociones WHERE inicio > :ahora", ahora=ahora)
        clientes = valor(
            "SELECT count(*) FROM usuarios WHERE nombre_usuario LIKE :patron",
            patron=f"{PREFIJO_CLIENTE}%",
        )
        tiquetes = valor("SELECT count(*) FROM tiquetes")
    print("=== Sembrado de la base de carga ===")
    for estado, tipo, cantidad in por_estado:
        print(f"vuelos {estado:<10} {tipo:<13} {cantidad:>7}")
    print(f"vuelos total                      {sum(fila[2] for fila in por_estado):>7}")
    print(f"rutas con vuelos programados      {rutas_con_vuelos:>7}")
    print(
        f"salida programada mínima / máxima {primera:%Y-%m-%d %H:%M} / {ultima:%Y-%m-%d %H:%M} UTC"
    )
    print(f"promociones (vigentes / futuras)  {promociones:>7} ({vigentes} / {futuras})")
    print(f"clientes {PREFIJO_CLIENTE}NNN        {clientes:>7}")
    print(f"tiquetes                          {tiquetes:>7}")
    print(f"semilla {args.semilla}, ventana de {args.dias} días, {segundos:.1f} s")


def sembrar(args: argparse.Namespace, url_base: str, nombre: str) -> None:
    inicio = reloj.monotonic()
    url = make_url(url_base)
    rng = random.Random(args.semilla)

    _recrear_base(url.set(database="postgres"), nombre, crear=True)
    _migrar(url_base)

    motor = create_engine(url)
    try:
        with Session(motor) as db:
            rutas = _rutas_validas(db)
        nacionales = sum(1 for ruta in rutas if ruta.tipo == "nacional")
        print(f"Rutas válidas: {nacionales} nacionales y {len(rutas) - nacionales} internacionales")

        metadatos = MetaData()
        metadatos.reflect(bind=motor, only=["vuelos", "promociones", "usuarios"])
        t_vuelos = metadatos.tables["vuelos"]
        t_promociones = metadatos.tables["promociones"]
        t_usuarios = metadatos.tables["usuarios"]

        ahora = datetime.now(UTC)
        hoy = datetime.now(ZONA_BOGOTA).date()
        vuelos = _vuelos_programados(rng, rutas, args.vuelos, hoy, args.dias)
        vuelos += _vuelos_con_estado(rng, rutas, args.realizados, hoy, "realizado", (-60, -1))
        vuelos += _vuelos_con_estado(
            rng, rutas, args.cancelados, hoy, "cancelado", (2, args.dias + 1)
        )
        _insertar(motor, t_vuelos, vuelos)

        with motor.connect() as conexion:
            programados = [
                (fila.id, fila.salida)
                for fila in conexion.execute(
                    t_vuelos.select()
                    .where(t_vuelos.c.estado == "programado")
                    .order_by(t_vuelos.c.id)
                )
            ]
        _insertar(motor, t_promociones, _promociones(rng, programados, args.promociones, ahora))
        _insertar(motor, t_usuarios, _clientes(args.clientes, hash_contrasena(CONTRASENA), ahora))

        with motor.begin() as conexion:
            conexion.execute(text("ANALYZE"))
        _resumen(motor, args, reloj.monotonic() - inicio)
    finally:
        motor.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Siembra la base *_carga de la prueba de carga.")
    parser.add_argument("--vuelos", type=int, default=10_000, help="vuelos programados")
    parser.add_argument("--realizados", type=int, default=1_000)
    parser.add_argument("--cancelados", type=int, default=200)
    parser.add_argument("--clientes", type=int, default=100)
    parser.add_argument("--dias", type=int, default=90, help="ventana de salidas, en días")
    parser.add_argument("--promociones", type=float, default=0.10, help="fracción de programados")
    parser.add_argument("--semilla", type=int, default=135)
    parser.add_argument("--limpiar", action="store_true", help="solo borra la base de carga")
    args = parser.parse_args()

    url_base = get_settings().database_url
    nombre = _nombre_de_base_de_carga(url_base)
    if args.vuelos + args.realizados + args.cancelados > MAXIMO_VUELOS:
        raise SystemExit("El código STA-xxxxx admite como mucho 99.999 vuelos.")

    if args.limpiar:
        _recrear_base(make_url(url_base).set(database="postgres"), nombre, crear=False)
        print(f"Base «{nombre}» borrada.")
        return
    sembrar(args, url_base, nombre)


if __name__ == "__main__":
    main()
