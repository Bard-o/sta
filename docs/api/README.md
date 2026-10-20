# Contrato de la API

Un archivo por módulo (`docs/api/<modulo>.md`) con sus endpoints, reglas y códigos de error. El contrato acordado de cada iteración, con todas sus HU y las funciones entre módulos, está en `iteracion-<n>.md`: [iteración 1](iteracion-1.md). La documentación interactiva, generada desde los `schemas.py`, está en http://localhost:8000/docs y el esquema en http://localhost:8000/openapi.json.

## Convenciones

- Prefijo `/api/v1`. JSON con claves en `snake_case`, en español y sin tildes ni eñes.
- Fechas y horas en ISO 8601 y en UTC. Dinero en COP como entero.
- Sesión en una cookie httpOnly (`sta_sesion`, `SameSite=Lax`, `Secure` en producción). El frontend llama a la API por el mismo origen (Vite reenvía `/api` al backend), así que no hay CORS ni tokens en JavaScript.

## Formato único de error

Toda respuesta de error, de cualquier módulo, tiene esta forma:

```json
{
  "error": {
    "codigo": "datos_invalidos",
    "mensaje": "Revisa los campos marcados.",
    "campos": { "contrasena": "Este campo es obligatorio." }
  }
}
```

- `codigo`: estable; el frontend decide con él.
- `mensaje`: en español, para mostrarle al usuario.
- `campos`: opcional; el error de cada campo (IU-07).

Los módulos lanzan las excepciones de `app/core/errors.py` (`SolicitudInvalida`, `NoAutenticado`, `SinPermiso`, `NoEncontrado`, `Conflicto`, `DatosInvalidos`, `DemasiadosIntentos`) o una subclase propia de `AppError` con su `codigo`.

| HTTP | `codigo` genérico | Cuándo |
|---|---|---|
| 400 | `solicitud_invalida` | La solicitud no tiene sentido para el estado actual. |
| 401 | `no_autenticado` | No hay sesión, o venció por inactividad (RNF-14). |
| 403 | `sin_permiso` | El rol no tiene permiso para la operación (RF-11, RNF-10). |
| 404 | `no_encontrado` | El recurso o la ruta no existen. |
| 409 | `conflicto` | Choca con el estado actual (p. ej. un dato único repetido). |
| 422 | `datos_invalidos` | El cuerpo o los parámetros no pasan la validación; trae `campos`. |
| 429 | `demasiados_intentos` | Límite de intentos (RNF-13). |
| 500 | `error_interno` | Error no controlado; el detalle queda en los logs. |

## Endpoints transversales

### `GET /api/v1/health`

Sin sesión. Responde `200` si el backend está arriba y alcanza la base de datos.

```json
{ "estado": "ok", "base_de_datos": "ok" }
```
