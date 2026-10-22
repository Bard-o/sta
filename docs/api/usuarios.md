# Módulo usuarios

Dueño: Backend A. Requisitos: RF-01 a RF-11. Este archivo cubre el registro de clientes (RF-03, RF-04, HU-01) y la sesión (RF-06, HU-03, HU-04); el resto de endpoints del módulo se agregan aquí con sus issues. El contrato acordado de todo el módulo está en [iteracion-1.md](iteracion-1.md).

## Registro de clientes

### `POST /api/v1/usuarios/registro`

Sin sesión (visitante). Crea la cuenta de cliente, inicia la sesión con la cookie y envía al
correo el enlace de verificación `/verificar-correo?token=…` (vence en 24 horas y sirve una
sola vez; el endpoint que lo consume es HU-02).

Entrada (`RegistroClienteEntrada`):

```json
{
  "tipo_documento": "CC",
  "numero_documento": "1088345921",
  "nombres": "Laura",
  "apellidos": "Gómez Ríos",
  "fecha_nacimiento": "1995-03-14",
  "lugar_nacimiento": "Pereira, Risaralda",
  "direccion_facturacion": "Cra. 7 # 19-28, Pereira",
  "genero": "femenino",
  "email": "laura.gomez@correo.co",
  "telefono": "310 555 0192",
  "nombre_usuario": "lauragomez",
  "contrasena": "Clave1234",
  "acepta_politica": true
}
```

- `acepta_politica` debe ser `true`; se guarda la fecha de aceptación (Ley 1581 de 2012).
- `fecha_nacimiento` no puede ser futura. No hay edad mínima de registro: un menor de edad
  puede registrarse (la restricción de edad aplica al volar).
- `contrasena`: 8 caracteres o más, con al menos una letra y un número (RNF-08); se guarda
  con Argon2id, nunca en claro.
- `nombre_usuario` es único en todo el sistema, sin distinguir mayúsculas. El correo y el
  documento (tipo y número) son únicos entre las cuentas de cliente, así que un administrador
  puede registrarse como cliente con sus mismos datos (SUP-18).
- La cuenta nace con `email_verificado: false` y sin suscripción a noticias. El monedero
  llega en la iteración 2. La imagen de perfil se sube después del registro, con
  `PUT /api/v1/usuarios/me/imagen`.
- Con una sesión abierta responde `403 sin_permiso`: solo el visitante se registra.
- Si el correo no se puede enviar, la cuenta queda creada igual y el fallo se anota en el
  log; el cliente puede pedir el reenvío (HU-02).

`201`: pone la cookie de sesión y devuelve el usuario.

```json
{
  "id": 12,
  "nombre_usuario": "lauragomez",
  "email": "laura.gomez@correo.co",
  "rol": "cliente",
  "email_verificado": false,
  "registro_completo": true,
  "nombres": "Laura",
  "apellidos": "Gómez Ríos"
}
```

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `datos_duplicados` | `campos` con `nombre_usuario`, `numero_documento` o `email` que ya pertenece a otra cuenta (RF-04). |
| 422 | `datos_invalidos` | `campos` con `acepta_politica`, `fecha_nacimiento`, `email`, `contrasena` o el campo con formato inválido. |
| 403 | `sin_permiso` | Hay una sesión abierta (Apéndice B). |

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
