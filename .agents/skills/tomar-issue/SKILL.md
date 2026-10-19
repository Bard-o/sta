---
name: tomar-issue
description: Resuelve un issue del repo STA de principio a fin. Lee el issue, crea la rama, implementa solo dentro del módulo, corre tests y lint y abre el PR con la plantilla. Úsala cuando te pidan tomar, resolver o implementar un issue.
---

# Tomar un issue

Sigue los pasos en orden. Las reglas de fondo están en `AGENTS.md`; esta skill no las repite todas.

## 1. Leer el issue

```bash
gh issue view <n> --comments
```

Antes de escribir código, anota:

- El módulo que toca y su dueño (tabla de `AGENTS.md`).
- Las HU y los RF/RNF que cita. Léelos en `docs/historias-de-usuario.md` y `docs/srs.md`, con sus criterios de aceptación y los supuestos SUP que referencian.
- El wireframe de cada HU en `docs/wireframes/<ID-HU>.png` y `DESIGN.md`, si el issue tiene interfaz.
- El contrato en `docs/api/<modulo>.md`.

Detente y comenta en el issue, sin implementar, si:

- Hace falta tocar otro módulo, `backend/app/core/`, Docker o CI.
- Necesitas una función que no existe en el `service.py` de otro módulo.
- El issue contradice el SRS, las HU o el contrato.

## 2. Crear la rama

```bash
git status                       # debe estar limpio
git switch main
git pull --ff-only
git switch -c feat/<n>-<slug>    # slug en kebab-case, sin tildes
```

## 3. Implementar dentro del módulo

Backend: solo `backend/app/modules/<modulo>/` (más una migración en `backend/alembic/versions/` si hace falta). Frontend: solo `frontend/`.

- Lógica de negocio en `service.py`; `router.py` solo valida, llama al service y responde.
- Entradas y salidas como modelos Pydantic en `schemas.py`. Si cambias uno que ya existe, es un cambio de contrato (paso 6).
- Para otro módulo, solo funciones públicas de su `service.py`.
- Errores con las excepciones de `app/core/`, en el formato único de `AGENTS.md`.
- ¿Cambia el modelo de datos? Sigue la skill `crear-migracion`.
- Frontend: lee `DESIGN.md` y cierra con su checklist. Solo componentes de `src/components/ui` (clases `sta-*`), solo tokens de `design/` y tipos de `src/api/schema.d.ts` (regenéralos con `npm run gen:api` si el backend cambió).

Haz commits pequeños con Conventional Commits en español: `feat(<modulo>): <descripción>`.

## 4. Tests

Cada criterio de aceptación de las HU y RF del issue tiene al menos un test. Nombra el test por el comportamiento y cita el ID en el docstring o en un comentario (`# HU-24: una reserva de 10 h antes de un vuelo nacional vence 1 h antes de la salida`).

```bash
docker compose run --rm backend uv run pytest app/modules/<modulo>
docker compose run --rm backend uv run pytest            # toda la suite antes del PR
docker compose run --rm frontend npm test
```

Si un test falla, arregla el código o el test. No lo desactives.

## 5. Lint

```bash
docker compose run --rm backend uv run ruff format .
docker compose run --rm backend uv run ruff check .
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
```

## 6. Abrir el PR

1. Actualiza la rama sobre `main` y vuelve a correr tests y lint:

   ```bash
   git fetch origin
   git rebase origin/main
   ```

   Si trae migración, verifica que `alembic heads` muestre un solo head (skill `crear-migracion`).

2. Sube la rama:

   ```bash
   git push -u origin feat/<n>-<slug>        # tras un rebase: git push --force-with-lease
   ```

3. Copia `.github/pull_request_template.md` a un archivo temporal, llénalo (`Closes #<n>`, tests, contrato, migración) y crea el PR:

   ```bash
   gh pr create --base main --title "feat(<modulo>): <descripción>" --body-file <archivo-llenado>
   ```

   Si cambiaste un schema existente, márcalo en la sección de contrato y menciona al dueño del frontend.

4. Responde con el enlace del PR y un resumen: qué hiciste, qué tests agregaste y cualquier punto que el revisor deba mirar.
