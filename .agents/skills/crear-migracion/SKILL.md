---
name: crear-migracion
description: Crea, revisa y valida una migración de Alembic en el repo STA, respetando la regla de un solo head y una migración por PR. Úsala cuando un cambio en models.py necesite migración o cuando `alembic heads` muestre más de un head.
---

# Crear una migración

Reglas: máximo una migración por PR, solo sobre las tablas de tu módulo, nunca editar una migración que ya está en `main` y nunca usar `alembic merge`.

## 1. Partir de main actualizado

```bash
git fetch origin
git rebase origin/main
docker compose run --rm backend uv run alembic upgrade head
docker compose run --rm backend uv run alembic heads   # debe mostrar exactamente un head
```

Si ya hay más de un head en `main`, no sigas: avisa al líder.

## 2. Cambiar el modelo

Edita solo `backend/app/modules/<modulo>/models.py`. Una llave foránea hacia otro módulo se declara con el nombre de su tabla (`ForeignKey("vuelos.id")`).

Alembic descubre los `models.py` de todos los módulos. Si el autogenerate no detecta tu tabla, no edites `alembic/env.py`: avisa en el issue.

## 3. Generar la migración

```bash
docker compose run --rm backend uv run alembic revision --autogenerate -m "<modulo>: <qué cambia>"
```

Revisa a mano el archivo nuevo en `backend/alembic/versions/`:

- Solo toca tablas de tu módulo. Borra cualquier operación sobre tablas ajenas.
- Un cambio de nombre de columna o tabla aparece como borrar y crear: cámbialo por `op.alter_column` u `op.rename_table` para no perder datos.
- Columnas nuevas `NOT NULL` en tablas con datos necesitan `server_default` o un paso de datos.
- `downgrade()` deshace exactamente lo que hace `upgrade()`.

## 4. Probarla

```bash
docker compose run --rm backend uv run alembic upgrade head
docker compose run --rm backend uv run alembic downgrade -1
docker compose run --rm backend uv run alembic upgrade head
docker compose run --rm backend uv run pytest app/modules/<modulo>
```

¿Necesitas más cambios de esquema en el mismo PR? No crees una segunda migración. Bájala (`docker compose run --rm backend uv run alembic downgrade -1`), borra el archivo, ajusta `models.py` y vuelve al paso 3.

## 5. Antes de pedir review: un solo head

```bash
git fetch origin
git rebase origin/main
docker compose run --rm backend uv run alembic heads
```

Si muestra un head, listo. Si muestra dos, otra migración entró a `main` mientras trabajabas. Regenera la tuya encima:

1. Abre tu archivo de migración y copia su `down_revision`.
2. Baja tu migración mientras el archivo todavía existe: `docker compose run --rm backend uv run alembic downgrade <down_revision>`.
3. Borra tu archivo de migración.
4. Aplica lo que llegó de `main`: `docker compose run --rm backend uv run alembic upgrade head`.
5. Repite los pasos 3 y 4 de esta skill.
6. Confirma que `docker compose run --rm backend uv run alembic heads` muestra un solo head y sube la rama con `git push --force-with-lease`.

En la plantilla del PR, marca que trae migración y que `alembic heads` da un solo head.
