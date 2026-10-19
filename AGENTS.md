# AGENTS.md

Guía para agentes de código (Codex, Cursor, OpenCode, Claude Code) y para las personas del equipo. Si una instrucción de un issue choca con este archivo, gana este archivo; pregunta en el issue.

STA es el Sistema de Tiquetes Aéreos de AVIANCO, una aerolínea ficticia (proyecto de Laboratorio de Software, UTP 2026-2). Antes de implementar, lee lo que aplica a tu issue:

- Requisitos: [`docs/srs.md`](docs/srs.md) (RF, RNF, supuestos SUP, apéndices con reglas de tiempo y permisos por rol).
- Historias: [`docs/historias-de-usuario.md`](docs/historias-de-usuario.md) (HU con criterios de aceptación) y su wireframe en `docs/wireframes/<ID-HU>.png`.
- Contrato de la API: `docs/api/`.
- Diseño visual: [`DESIGN.md`](DESIGN.md) (reglas) y `design/` (tokens, estilos, fuentes y referencia de componentes).

## Stack

- Docker Compose con cuatro servicios: `db` (PostgreSQL), `backend`, `frontend` y `mailpit` (SMTP de desarrollo; bandeja en http://localhost:8025).
- Backend: FastAPI + SQLAlchemy 2.0 **síncrono** (nada de `async def` con la base de datos ni drivers async) + Alembic + Pydantic v2. Dependencias con uv (`pyproject.toml` + `uv.lock`).
- Frontend: Vite + React + TypeScript + React Router + TanStack Query + Tailwind v4 + shadcn/ui. Dependencias con npm (`package.json` + `package-lock.json`).
- Los tipos de la API en el frontend se generan desde `/openapi.json` del backend y nunca se escriben a mano.

## Comandos

Todo se ejecuta con `docker compose`. Nadie instala Python, Node ni dependencias en su máquina. Mientras no exista el andamiaje del proyecto, esta lista es el contrato que ese andamiaje debe cumplir.

```bash
# Entorno
docker compose up -d --build        # levantar todo; también tras cambiar dependencias o un Dockerfile
docker compose up -d                # levantar sin reconstruir
docker compose logs -f backend      # ver logs de un servicio
docker compose down                 # apagar (conserva la base de datos)

# Backend: tests y lint
docker compose run --rm backend uv run pytest
docker compose run --rm backend uv run pytest app/modules/<modulo>
docker compose run --rm backend uv run ruff check .
docker compose run --rm backend uv run ruff format --check .
docker compose run --rm backend uv run ruff format .          # corrige el formato

# Backend: migraciones (procedimiento completo en la skill crear-migracion)
docker compose run --rm backend uv run alembic upgrade head
docker compose run --rm backend uv run alembic heads
docker compose run --rm backend uv run alembic revision --autogenerate -m "<modulo>: <qué cambia>"

# Frontend: tests, lint y tipos
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm run gen:api              # regenera src/api/schema.d.ts; requiere el backend arriba
docker compose run --rm frontend npm run tokens               # regenera design/tokens.css desde design/tokens.json

# Dependencias (agregar una nueva; subir versiones requiere issue)
docker compose run --rm backend uv add <paquete>
docker compose run --rm frontend npm install <paquete>
docker compose run --rm frontend npx shadcn@latest add <componente>
```

URLs locales: frontend http://localhost:5173, API http://localhost:8000/api/v1, documentación interactiva http://localhost:8000/docs.

## Estructura y dueños

```text
backend/
  app/
    core/                 # configuración, sesión de BD, seguridad, formato de error, correo, fixtures de tests
    modules/
      <modulo>/
        router.py         # endpoints
        schemas.py        # modelos Pydantic de entrada y salida (el contrato)
        service.py        # lógica de negocio; sus funciones públicas son la interfaz del módulo
        models.py         # modelos SQLAlchemy
        tests/
  alembic/versions/
frontend/
  src/
    api/schema.d.ts       # generado, no se edita
    components/ui/        # componentes del sistema de diseño (clases sta-*)
design/                   # tokens.json, tokens.css (generado), components.css, fonts/, reference/
docs/                     # srs.md, historias-de-usuario.md, wireframes/, api/
.agents/skills/           # procedimientos para agentes
DESIGN.md                 # reglas visuales
```

Cada módulo tiene un dueño. Un agente solo toca el módulo del issue que está resolviendo.

| Módulo | Requisitos | Dueño |
|---|---|---|
| `usuarios` | RF-01 a RF-11 | Backend A |
| `busqueda` | RF-27 a RF-29 | Backend A |
| `noticias` | RF-22, RF-25, RF-55, RF-56 | Backend A |
| `muro` | RF-57 a RF-59 | Backend A |
| `monedero` | RF-46 a RF-48 | Backend A |
| `vuelos` (incluye promociones) | RF-12 a RF-21, RF-23, RF-24 | Backend B |
| `reservas` (carrito, reserva, compra, sillas, cancelaciones) | RF-30 a RF-45 | Backend B |
| `checkin` | RF-49 a RF-54 | Backend B |
| `auditoria` | RF-26, RNF-16 | Backend B |
| `recomendacion` | RF-60 a RF-64 | Líder |
| `chatbot` | RF-65 a RF-71 | Líder |
| `frontend/` | toda la interfaz | Frontend |
| `DESIGN.md`, `design/` | sistema de diseño | Frontend |
| `backend/app/core/`, Docker, CI (`.github/`), `AGENTS.md`, `.agents/` | infraestructura | Líder |

Reglas entre módulos:

- Si necesitas algo de otro módulo, llama solo a las funciones públicas (sin `_` inicial) de su `service.py`. No importes su `models.py`, `schemas.py` ni `router.py`.
- Una llave foránea hacia otro módulo se declara con el nombre de la tabla (`ForeignKey("vuelos.id")`), sin importar el modelo.
- Si la función que necesitas no existe, no la escribes tú: comenta en el issue para que el dueño la agregue.
- Cambiar `core/`, Docker o CI requiere un issue propio. Si tu issue no se puede resolver sin tocarlos, detente y avisa en el issue.

## Flujo por issue

El paso a paso para agentes está en la skill [`tomar-issue`](.agents/skills/tomar-issue/SKILL.md).

1. Rama `feat/<n>-<slug>` desde `main` actualizado (`n` = número del issue; slug en kebab-case sin tildes). Ejemplo: `feat/12-registro-clientes`.
2. Commits con Conventional Commits en español: `tipo(alcance): descripción`, en minúscula y sin punto final. Tipos: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `build`, `ci`. El alcance es el módulo. Ejemplos: `feat(vuelos): calcula la llegada en hora local del destino`, `fix(reservas): libera las sillas al vencer la reserva`.
3. PR con la plantilla de `.github/pull_request_template.md`, `Closes #n` en la descripción y el título en formato Conventional Commits (será el mensaje del squash).
4. Para mergear: CI en verde y 1 aprobación. El líder revisa todos los PRs.
5. Squash merge. Borra la rama después.

## API y contrato

- Prefijo `/api/v1`. JSON con claves en `snake_case`. Rutas, campos y nombres del dominio en español, sin tildes ni eñes (`/api/v1/vuelos`, `precio_economica`).
- El contrato es la fuente de verdad: `docs/api/<modulo>.md` (endpoints, reglas, códigos de error) y los `schemas.py`. Primero se acuerda el contrato, luego se implementa.
- Un único formato de error para toda la API. Los módulos lanzan las excepciones de `app/core/`; no arman respuestas de error a mano ni devuelven el `detail` por defecto de FastAPI.

  ```json
  {
    "error": {
      "codigo": "vuelo_con_reservas",
      "mensaje": "El vuelo tiene reservas activas y no se puede editar.",
      "campos": { "precio_economica": "Debe ser un entero mayor que 0." }
    }
  }
  ```

  `codigo` es estable y el frontend decide con él; `mensaje` está en español para el usuario; `campos` es opcional y lleva el error de cada campo (IU-07 del SRS).
- Fechas y horas en ISO 8601 y en UTC (RF-15); la hora local se calcula para mostrarla. Dinero en COP como entero, sin decimales (IU-06).
- Si cambias un schema que ya existe, el PR lo dice explícitamente en la sección de contrato de la plantilla y menciona al dueño del frontend. Agregar un endpoint nuevo también se documenta en `docs/api/`.
- Los tipos del frontend los regenera el frontend en su propia rama con `npm run gen:api`.

## Migraciones

El procedimiento completo está en la skill [`crear-migracion`](.agents/skills/crear-migracion/SKILL.md).

- Máximo una migración por PR, y solo sobre las tablas de tu módulo.
- Antes de pedir review: rebase sobre `main` y verifica que `alembic heads` muestre un solo head.
- Nunca edites una migración que ya está en `main`. Si tiene un error, se corrige con una migración nueva.
- No uses `alembic merge`. Si quedan dos heads, regenera tu migración sobre el head actual.

## Frontend

- Lee [`DESIGN.md`](DESIGN.md) antes de crear o cambiar una pantalla y termina con su checklist. Las reglas están ahí; los valores, en `design/tokens.json`.
- Usa solo componentes de `src/components/ui`: son los del sistema de diseño (`Button`, `Glass`, `FlightPass`, `SeatMap`…) reimplementados con las clases `sta-*` de `design/components.css` y las props de `design/reference/components.d.ts`. shadcn/ui sirve como base de comportamiento accesible, pintada con `sta-*`. Si falta un componente, se agrega ahí, no dentro de una pantalla.
- Toda variable visual sale de un token: `var(--accent)` o la utilidad de Tailwind mapeada a ese token. Nada de hex, rgba ni valores arbitrarios de Tailwind como `bg-[#1f2937]`.
- `design/tokens.css` es generado: cambia `design/tokens.json` y corre `npm run tokens`.
- El contenedor del frontend monta `design/` en la misma ruta relativa que en el repo; Vite la expone con el alias `@design` y `npm run tokens` ejecuta `node ../design/build-tokens.mjs`.
- Los tipos de la API se importan de `src/api/schema.d.ts`. Los datos del servidor se manejan con TanStack Query.
- Los textos de la interfaz van en español de Colombia (IU-08). Fechas `dd/mm/aaaa`, horas de 24 h y dinero con separador de miles de punto (IU-05, IU-06).
- Cada pantalla tiene su wireframe en `docs/wireframes/`; respeta su estructura y sus estados (errores, bloqueos, avisos).

## Prohibido

- Commitear `.env`.
- Subir versiones de dependencias sin un issue.
- Desactivar tests o lint (`skip`, `xfail`, `# noqa`, `eslint-disable`, `@ts-ignore`, bajar umbrales).
- El repo es público: nada de credenciales reales, datos personales ni material del profesor en ningún archivo. El `.env.example` lleva solo valores de ejemplo.
