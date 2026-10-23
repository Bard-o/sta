# Módulo usuarios

Dueño: Backend A. Requisitos: RF-01 a RF-11. Este archivo cubre el registro de clientes (RF-03, RF-04, HU-01), la verificación de correo (RF-05, HU-02), la sesión (RF-06, HU-03, HU-04) y el cambio de contraseña (HU-06); el resto de endpoints del módulo se agregan aquí con sus issues. El contrato acordado de todo el módulo está en [iteracion-1.md](iteracion-1.md).

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

## Verificación de correo

### `POST /api/v1/usuarios/verificacion`

Sin sesión (público). Recibe el token del enlace `/verificar-correo?token=…` y responde `204` sin cuerpo.

Entrada (`TokenEntrada`):

```json
{ "token": "…" }
```

- El token se guarda hasheado (SHA-256); el valor en claro solo viaja en el enlace del correo.
- Es de un solo uso y vence a las 24 horas (SUP-19). Al usarlo, los demás tokens vigentes de la cuenta quedan invalidados.
- Marca `email_verificado` como `true`, lo que habilita reservar, comprar y suscribirse a noticias.
- No exige sesión: el enlace se puede abrir en otro dispositivo.
- El cambio de correo desde el perfil (HU-07) reutiliza este endpoint; el correo pendiente se documenta con esa historia.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `enlace_invalido` | Token inexistente, vencido, ya usado o de otro correo. El frontend ofrece reenviar. |
| 422 | `datos_invalidos` | Falta `token` o está vacío. |

### `POST /api/v1/usuarios/me/verificacion/reenviar`

Con sesión de cliente o administrador. Envía un enlace nuevo al correo vigente de la cuenta y responde `204` sin cuerpo. El root no puede usarlo.

- Reenviar invalida todos los enlaces vigentes anteriores de la cuenta.
- Si el correo ya está verificado no hay nada pendiente que reenviar.
- Si el correo no se puede enviar, el enlace queda creado igual y el fallo se anota en el log; el cliente puede volver a pedirlo.
- El enlace tiene la misma vigencia de 24 horas y también es de un solo uso.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `correo_ya_verificado` | El correo ya está verificado (o la cuenta no tiene correo). |
| 401 | `no_autenticado` | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | El rol no es cliente ni administrador. |

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

## Contraseña

### `PUT /api/v1/usuarios/me/contrasena`

Con sesión de cualquier rol (cliente, admin o root). Cambia la contraseña indicando la actual (HU-06, RF-08). Es la única forma en que el root cambia la suya, porque no tiene correo (RF-01). Responde `204` sin cuerpo.

Entrada:

```json
{ "contrasena_actual": "Clave1234", "contrasena_nueva": "OtraClave99", "confirmacion": "OtraClave99" }
```

- La contraseña nueva cumple RNF-08: mínimo 8 caracteres, al menos una letra y un número. Se guarda como hash Argon2id, nunca en texto plano.
- Las validaciones de `contrasena_nueva` y `confirmacion` se hacen antes de comprobar la actual.
- La sesión actual sigue abierta: este cambio no invalida ninguna sesión (a diferencia del restablecimiento de HU-05, que las cierra todas).

| HTTP | `codigo` | `campos` | Cuándo |
|---|---|---|---|
| 422 | `contrasena_actual_incorrecta` | `contrasena_actual` | La contraseña actual no coincide; no se cambia nada. |
| 422 | `datos_invalidos` | `contrasena_nueva` | No cumple la política de RNF-08. |
| 422 | `datos_invalidos` | `confirmacion` | No coincide con la contraseña nueva. |
| 401 | `no_autenticado` | | Sin sesión, token inválido o sesión vencida. |

## Usuario root

`python -m app.seed` (lo corre el contenedor del backend al arrancar) crea el root con `ROOT_USERNAME` y `ROOT_PASSWORD` del `.env` si todavía no existe un usuario con rol root. Si ya existe, no lo modifica: el root cambia su contraseña desde su sesión (RF-01).
