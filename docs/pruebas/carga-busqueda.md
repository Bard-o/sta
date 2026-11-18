# Prueba de carga · Búsqueda de vuelos (RNF-01)

Medición de RNF-01 sobre `GET /busqueda/vuelos` y `GET /busqueda/regresos` con 100 usuarios concurrentes y unos 10.000 vuelos programados (issue [#135](https://github.com/Bard-o/sta/issues/135)). Fecha: 18/11/2026, de 03:33 a 03:45 (hora de Colombia). Código medido: rama `feat/135-prueba-carga-busqueda` en `0e65690` (sobre `main` en `76f4c55`).

Leyenda: ✅ cumple · ❌ falla

**Resultado:** ✅ cumple con amplio margen. En la meseta de 10 minutos, el p95 de `/busqueda/vuelos` es de 54 ms y el de `/busqueda/regresos` de 48 ms (límite: 2.000 ms), el p99 no pasa de 105 ms (límite del SRS: 4.000 ms) y no falló ninguna de las 58.266 peticiones.

## Entorno

- Portátil AMD Ryzen 5 5500U (6 núcleos, 12 hilos), 14 GiB de RAM, Linux 7.2.5, Docker 29.7.2 y Compose 5.5.1.
- PostgreSQL 16.15 (servicio `db`, `max_connections=100`), en la misma máquina que el backend y el generador de carga, por la red de Compose.
- Backend `backend-carga` (perfil `carga`): la misma imagen del backend con `uvicorn --workers 4`, sin `--reload` y sin access log. Cuatro procesos son un despliegue pequeño típico, dejan unos 8 hilos para PostgreSQL y k6, y caben en `max_connections` con el pool por defecto de SQLAlchemy (4 × 15 = 60 conexiones). Planificador apagado (`PLANIFICADOR_ACTIVO=false`) y `COOKIE_SECURE=false` porque se habla por http dentro de Compose.
- Generador de carga: k6 v2.4.0 (`grafana/k6:2.4.0`).
- Arriba durante la medición, además: `db` y `mailpit` (sin backend ni frontend de desarrollo).
- Uso de recursos a mitad de la meseta (`docker stats`, minutos 5 y 6): `backend-carga` 123–142 % de CPU (de 1.200 %) y 530 MiB; `db` 62–74 % y 138 MiB; k6 10–11 % y 172 MiB.

## Volumen de datos

Generados por `backend/scripts/carga/sembrar.py` en una base aparte, `sta_carga`, que el script crea, migra con Alembic, siembra y borra. Semilla 135; tardó 1,9 s.

| Dato | Cantidad |
|---|---:|
| Vuelos programados nacionales | 8.000 |
| Vuelos programados internacionales | 2.000 |
| Vuelos realizados (los últimos 60 días) | 1.000 |
| Vuelos cancelados | 200 |
| Rutas con vuelos programados | 979 de 1.042 permitidas (RF-14) |
| Salidas programadas | del 20/11/2026 al 18/02/2027 (90 días, desde dos días después del sembrado) |
| Promociones (vigentes / por empezar) | 1.000 (984 / 16) |
| Clientes verificados `carga_cliente_001` a `carga_cliente_100` | 100 |
| Tiquetes | 0 |

Las rutas se eligen con pesos por ciudad (los hubs concentran los vuelos) y las horas de salida tienen picos de mañana y de tarde. Los precios crecen con la duración, como los del catálogo.

## Escenario

`carga/busqueda.js`: 1 minuto de rampa hasta 100 usuarios virtuales, 10 minutos de meseta con 100 y 30 segundos de bajada. Los umbrales se evalúan solo en la meseta, que es el método de RNF-01.

- La mitad de los usuarios virtuales inicia sesión como cliente al empezar (50 cuentas distintas) y la otra mitad busca como visitante. Las búsquedas de los clientes se registran (HU-20).
- Cada iteración hace una búsqueda de `/vuelos` con una combinación de filtros y un orden al azar. El 25 % pide también la página 2. El 35 % hace además ida y regreso (HU-21): busca la ida exacta y luego `/regresos` desde su destino.
- Combinaciones de filtros: sin filtros, origen, origen y destino, origen en una semana, precio y clase (el ejemplo de HU-20), internacionales en una quincena, destino en primera con precio máximo, origen con franja horaria y duración, nacionales por duración en un mes, y código. Los tres órdenes (`precio`, `fecha`, `duracion`) salen al azar.
- Pausa entre peticiones de 0,5 a 1,5 s.

## Resultados (meseta)

- Peticiones: 58.266 (97,1 por segundo). Fallidas: 0 (0,000 %).
- Comprobaciones (status 200, `items` es una lista, login y sesión): 100 %.
- Iteraciones de toda la corrida: 32.137. Regresos con al menos un resultado: 54 %.

### Por endpoint (ms)

| Endpoint | Peticiones | p50 | p90 | p95 | p99 | máx | Umbral |
|---|---:|---:|---:|---:|---:|---:|---|
| `/busqueda/vuelos` | 47.788 | 26,2 | 45,1 | 54,0 | 104,6 | 337,5 | ✅ |
| `/busqueda/regresos` | 10.478 | 19,5 | 38,5 | 48,4 | 96,6 | 313,6 | ✅ |
| todas | 58.266 | 24,9 | 44,2 | 53,4 | 102,0 | 337,5 | informativo |

### Por orden (ms)

| Endpoint y orden | Peticiones | p50 | p90 | p95 | p99 | máx | Umbral |
|---|---:|---:|---:|---:|---:|---:|---|
| `vuelos` precio | 15.936 | 26,8 | 46,2 | 55,2 | 102,9 | 263,7 | ✅ |
| `vuelos` fecha | 15.831 | 26,1 | 44,4 | 53,5 | 97,1 | 295,6 | ✅ |
| `vuelos` duracion | 16.021 | 25,9 | 44,6 | 53,5 | 111,5 | 337,5 | ✅ |
| `regresos` precio | 3.547 | 19,7 | 39,0 | 49,0 | 94,8 | 224,5 | ✅ |
| `regresos` fecha | 3.495 | 19,5 | 37,9 | 47,7 | 105,8 | 313,6 | ✅ |
| `regresos` duracion | 3.436 | 19,3 | 38,7 | 48,3 | 87,2 | 220,4 | ✅ |

### Con y sin sesión (ms)

| Endpoint y sesión | Peticiones | p50 | p90 | p95 | p99 | máx | Umbral |
|---|---:|---:|---:|---:|---:|---:|---|
| `vuelos` cliente | 23.830 | 29,5 | 49,5 | 59,7 | 139,6 | 337,5 | ✅ |
| `vuelos` visitante | 23.958 | 22,8 | 39,7 | 47,0 | 76,0 | 249,7 | ✅ |
| `regresos` cliente | 5.221 | 23,0 | 44,0 | 56,2 | 135,2 | 313,6 | ✅ |
| `regresos` visitante | 5.257 | 15,4 | 31,7 | 39,4 | 67,6 | 212,5 | ✅ |

Con sesión cuesta unos 7 ms más en la mediana: se valida la cookie y la primera página se registra con su propio `commit`.

### Por combinación de filtros de `vuelos` (ms)

| Combinación | Peticiones | p50 | p90 | p95 | p99 | máx | Umbral |
|---|---:|---:|---:|---:|---:|---:|---|
| `sin_filtros` | 3.769 | 36,6 | 53,3 | 62,3 | 109,9 | 283,4 | ✅ |
| `origen` | 3.622 | 23,2 | 41,3 | 51,0 | 104,9 | 256,7 | ✅ |
| `origen_destino` | 3.698 | 21,2 | 39,8 | 50,7 | 135,3 | 254,1 | ✅ |
| `origen_semana` | 3.819 | 22,1 | 39,6 | 48,4 | 106,2 | 271,8 | ✅ |
| `precio_clase` | 3.714 | 23,4 | 40,1 | 49,4 | 121,6 | 294,7 | ✅ |
| `internacional_quincena` | 3.651 | 27,4 | 44,0 | 53,1 | 84,4 | 249,7 | ✅ |
| `destino_primera_precio` | 3.879 | 25,5 | 43,0 | 52,2 | 94,0 | 225,8 | ✅ |
| `origen_franja_duracion` | 3.707 | 22,7 | 41,3 | 51,3 | 103,3 | 266,6 | ✅ |
| `nacional_duracion_mes` | 3.652 | 32,3 | 49,2 | 58,4 | 97,9 | 234,5 | ✅ |
| `codigo` | 3.799 | 37,3 | 53,8 | 63,5 | 124,6 | 245,3 | ✅ |
| `ida_exacta` (ida del recorrido de ida y regreso) | 10.478 | 20,3 | 38,6 | 47,6 | 90,4 | 337,5 | ✅ |

Las más lentas son `sin_filtros` y `codigo`, que recorren casi todos los vuelos programados (el filtro por código es un `ILIKE` que busca el texto en cualquier parte del código), y aun así su p95 queda por debajo de 65 ms.

Inicio de sesión (informativo, fuera de los umbrales): 100 peticiones entre `POST /auth/login` y `GET /auth/me`, p95 de 74,6 ms.

## Registro de búsquedas

- `busquedas` en `sta_carga` pasó de 2.123 filas (antes de la corrida, por la prueba de humo) a 29.415: 27.292 nuevas, exactamente las que k6 contó como registrables (primera página de un cliente con respuesta 200).
- Las 29.415 filas son de 50 usuarios distintos, los 50 clientes: las búsquedas de visitantes no se registran (HU-20).

## Base de desarrollo intacta

- Antes y después, la base de desarrollo tenía 26 vuelos, 5 promociones y 28 usuarios, en la revisión `e39140d3a16f`.
- Después de `--limpiar`, `sta_carga` ya no existe.
- El sembrado se niega a correr si `DATABASE_URL` no apunta a una base cuyo nombre termine en `_carga` o si es la de `POSTGRES_DB`.

## Cumplimiento

- ✅ RNF-01: p95 ≤ 2 s en `/busqueda/vuelos` (54 ms), también en cada uno de los tres órdenes y en cada combinación de filtros.
- ✅ p95 ≤ 2 s en `/busqueda/regresos` (48 ms) y en cada orden.
- ✅ p99 ≤ 4 s, que el SRS pide además del p95 (105 ms en `/vuelos`, 97 ms en `/regresos`).
- ✅ Con y sin sesión de cliente, y las búsquedas de los clientes quedan registradas.
- ✅ Errores por debajo del 1 % (0 %).

## Limitaciones

- El generador de carga, el backend y PostgreSQL comparten la misma máquina. Con el uso de CPU medido (unos 2 de 12 hilos), no fue el cuello de botella.
- Unos 10.000 vuelos, como fija el issue. RNF-07 habla de 50.000 vuelos y un millón de tiquetes: el sembrado admite `--vuelos 50000`, pero no genera tiquetes, así que la ocupación de cada vuelo es 0.
- Sin TLS ni proxy delante del backend, y con el pool de conexiones por defecto de SQLAlchemy.

## Cómo repetirla

Desde la raíz del repositorio, con `db` y `mailpit` arriba. Mientras corre, no ejecutes pytest ni compilaciones: compiten por la CPU.

```bash
docker compose --profile carga build backend-carga
docker compose --profile carga run --rm backend-carga uv run python -m scripts.carga.sembrar
docker compose --profile carga up -d --wait backend-carga
docker compose --profile carga run --rm k6 run -e RAMPA=10s -e DURACION=30s /carga/busqueda.js  # humo
docker compose --profile carga run --rm k6                                                     # medición
docker compose --profile carga rm -sf backend-carga
docker compose --profile carga run --rm backend-carga uv run python -m scripts.carga.sembrar --limpiar
```

k6 deja el resumen en `carga/resultados/resumen.md` y `resumen.json` (ignorados por git) y sale con código 99 si algún umbral falla. No uses `docker compose --profile carga down`: también apaga los servicios de desarrollo. Los servicios del perfil `carga` no arrancan con `docker compose up`.
