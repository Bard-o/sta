## Qué cambia

<!-- Una a tres líneas: qué hace este PR y para qué. -->

Closes #

## Checklist

- [ ] Cierra un issue (`Closes #n` arriba) y la rama es `feat/<n>-<slug>`.
- [ ] Solo toca mi módulo, o el issue autoriza lo contrario.
- [ ] Cada criterio de aceptación del issue tiene al menos un test.
- [ ] Tests y lint pasan con `docker compose run --rm ...`.
- [ ] Hice rebase sobre `main` justo antes de pedir review.

## ¿Cambia el contrato de la API?

- [ ] No.
- [ ] Sí, agrega endpoints o schemas nuevos, documentados en `docs/api/`.
- [ ] Sí, cambia un schema que ya existe. Qué cambió y por qué: <!-- describe el cambio --> · @<!-- dueño del frontend -->

## ¿Trae migración?

- [ ] No.
- [ ] Sí, una sola, y después del rebase `alembic heads` muestra un solo head.
