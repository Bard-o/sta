# Módulo usuarios

Dueño: Backend A. Requisitos: RF-01 a RF-11. Este archivo cubre por ahora la sesión (RF-06, HU-03, HU-04); el resto de endpoints del módulo se agregan aquí con sus issues.

## Sesión

La sesión es un JWT firmado dentro de la cookie httpOnly `sta_sesion`.

- Vence por inactividad (RNF-14): 30 minutos para clientes, 15 para administradores y root. Cada petición autenticada renueva la cookie (como mucho una vez por minuto).
- Cerrar sesión la invalida en el servidor (HU-04): el token anterior deja de servir aunque alguien lo haya copiado. Hoy se invalidan todas las sesiones abiertas del usuario.
- Una cuenta desactivada pierde la sesión en la siguiente petición.

Para proteger un endpoint en otro módulo:

```python
from typing import Annotated

from app.core.auth import UsuarioActual, UsuarioSesion, require_role
from app.core.security import Rol

@router.post("/reservas")
def reservar(usuario: Annotated[UsuarioActual, Depends(require_role(Rol.CLIENTE))]): ...

@router.get("/algo")
def algo(usuario: UsuarioSesion): ...  # cualquier rol con sesión
```

### `POST /api/v1/auth/login`

Sin sesión. Inicia sesión con nombre de usuario o correo (sin distinguir mayúsculas) y contraseña.

Entrada:

```json
{ "usuario": "lauragomez", "contrasena": "Clave1234" }
```

`200`: pone la cookie de sesión y devuelve el usuario.

```json
{
  "id": 12,
  "nombre_usuario": "lauragomez",
  "email": "laura@example.com",
  "rol": "cliente",
  "email_verificado": true
}
```

`rol` es `root`, `admin` o `cliente`. El root no tiene correo (`email: null`, RF-01).

| HTTP | `codigo` | `mensaje` | Cuándo |
|---|---|---|---|
| 401 | `credenciales_invalidas` | Usuario o contraseña incorrectos. | Usuario inexistente o contraseña errada: el mensaje no dice cuál (RF-06). |
| 403 | `cuenta_inactiva` | Cuenta inactiva. | Credenciales correctas de una cuenta desactivada (RF-02, RF-10). |
| 422 | `datos_invalidos` | Revisa los campos marcados. | Falta `usuario` o `contrasena`. |

Pendiente para el issue de HU-03: bloqueo de 15 minutos tras 5 intentos fallidos (RNF-13, código `demasiados_intentos`).

### `POST /api/v1/auth/logout`

Con o sin sesión. Invalida la sesión en el servidor y borra la cookie. Responde `204` sin cuerpo.

### `GET /api/v1/auth/me`

Con sesión de cualquier rol. Devuelve el usuario de la sesión, con el mismo cuerpo que el login.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 401 | `no_autenticado` | Sin cookie, token alterado, sesión vencida o cerrada, o cuenta desactivada. |

## Usuario root

`python -m app.seed` (lo corre el contenedor del backend al arrancar) crea el root con `ROOT_USERNAME` y `ROOT_PASSWORD` del `.env` si todavía no existe un usuario con rol root. Si ya existe, no lo modifica: el root cambia su contraseña desde su sesión (RF-01).
