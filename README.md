# STA · Sistema de Tiquetes Aéreos de AVIANCO

Proyecto de Laboratorio de Software (UTP, 2026-2). AVIANCO es una aerolínea ficticia.

- Requisitos: [`docs/srs.md`](docs/srs.md) · Historias: [`docs/historias-de-usuario.md`](docs/historias-de-usuario.md) · Contrato de la API: [`docs/api/`](docs/api/)
- Diseño visual: [`DESIGN.md`](DESIGN.md)
- Cómo trabajamos (ramas, commits, PRs, módulos y dueños): [`AGENTS.md`](AGENTS.md)

## Requisitos

Solo necesitas **Git** y **Docker** con Docker Compose v2. No instales Python, Node ni dependencias en tu máquina: todo corre en contenedores.

- **Linux**: Docker Engine y el plugin `docker compose`. Agrega tu usuario al grupo `docker` (`sudo usermod -aG docker $USER` y vuelve a iniciar sesión) para no usar `sudo`.
- **Windows**: instala WSL2 con Ubuntu y Docker Desktop con la integración de WSL2 activada. **Clona el repo dentro de WSL2** (por ejemplo en `~/proyectos/sta`), no en `C:\` ni en `/mnt/c/...`: desde el disco de Windows la recarga en caliente no detecta los cambios y todo va mucho más lento. Abre el proyecto con VS Code y la extensión WSL (`code .` desde la terminal de Ubuntu).
- **macOS**: Docker Desktop.

## Levantar el proyecto

```bash
git clone https://github.com/Bard-o/sta.git
cd sta
cp .env.example .env
docker compose up -d --build
```

La primera vez tarda unos minutos. Al arrancar, el backend aplica las migraciones y crea el usuario root con `ROOT_USERNAME` y `ROOT_PASSWORD` del `.env`.

| Servicio | URL |
|---|---|
| Frontend (Vite, recarga en caliente) | http://localhost:5173 |
| API | http://localhost:8000/api/v1 |
| Documentación interactiva de la API | http://localhost:8000/docs |
| Correo de desarrollo (mailpit) | http://localhost:8025 |
| PostgreSQL | `localhost:5432` (usuario, clave y base en `.env`) |

Entra a http://localhost:5173/login con el root del `.env` (`root` / `CambiaEsta123` en el ejemplo).

Comandos del día a día:

```bash
docker compose up -d               # levantar sin reconstruir
docker compose logs -f backend     # ver logs de un servicio
docker compose down                # apagar (conserva la base de datos)
docker compose down -v             # apagar y borrar la base de datos y node_modules
```

Reconstruye con `docker compose up -d --build` cuando cambien dependencias (`pyproject.toml`, `package.json`) o un Dockerfile.

## Tests y lint

Backend (pytest usa una base de datos aparte, `sta_test`, que se crea y migra sola en cada corrida):

```bash
docker compose run --rm backend uv run pytest
docker compose run --rm backend uv run ruff check .
docker compose run --rm backend uv run ruff format --check .
```

Frontend:

```bash
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run format:check
docker compose run --rm frontend npm run typecheck
```

Tipos de la API (con el backend arriba; haz commit de `frontend/src/api/schema.d.ts`):

```bash
docker compose run --rm frontend npm run gen:api
```

Migraciones: ver la skill [`crear-migracion`](.agents/skills/crear-migracion/SKILL.md). La lista completa de comandos está en [`AGENTS.md`](AGENTS.md#comandos).

## Integración continua

Cada PR corre en GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) con los mismos comandos de `docker compose`: ruff, pytest, eslint, prettier, tsc y vitest. Además falla si `uv.lock` no está al día, si Alembic tiene más de un head, si los modelos tienen cambios sin migración, si `design/tokens.css` no coincide con `tokens.json` o si `frontend/src/api/schema.d.ts` no coincide con el `/openapi.json` del backend.

## Estructura

```text
backend/            FastAPI + SQLAlchemy 2.0 (síncrono) + Alembic
  app/core/         configuración, BD, seguridad, sesión, errores, correo, fixtures de tests
  app/modules/      un paquete por módulo (router, schemas, service, models, tests)
  alembic/versions/ migraciones
frontend/           Vite + React + TypeScript + TanStack Query + Tailwind v4
  src/api/          schema.d.ts (generado) y cliente tipado
  src/components/ui componentes del sistema de diseño (clases sta-*)
design/             tokens, estilos de componentes y fuentes
docs/               SRS, historias de usuario, wireframes y contrato de la API
```
