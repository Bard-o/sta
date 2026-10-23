# Módulo usuarios

Dueño: Backend A. Requisitos: RF-01 a RF-11. Este archivo cubre el registro de clientes (RF-03, RF-04, HU-01), la verificación de correo (RF-05, HU-02), la sesión (RF-06, HU-03, HU-04), el restablecimiento de contraseña (RF-07, HU-05), el cambio de contraseña (HU-06), el perfil (HU-07) y la desactivación de la cuenta (RF-10, HU-09); el resto de endpoints del módulo se agregan aquí con sus issues. El contrato acordado de todo el módulo está en [iteracion-1.md](iteracion-1.md).

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
- Si el token corresponde al correo pendiente de un cambio de perfil (HU-07), ese correo pasa a ser el de la cuenta, se limpia `email_pendiente` y queda verificado.
- Si otra cuenta del mismo rol tomó ese correo entre el cambio de perfil y la verificación, responde `409 datos_duplicados` con `campos.email`.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `enlace_invalido` | Token inexistente, vencido, ya usado o de otro correo. El frontend ofrece reenviar. |
| 409 | `datos_duplicados` | El correo pendiente ya pertenece a otra cuenta del mismo rol. |
| 422 | `datos_invalidos` | Falta `token` o está vacío. |

### `POST /api/v1/usuarios/me/verificacion/reenviar`

Con sesión de cliente o administrador. Envía un enlace nuevo al correo pendiente si hay un cambio de perfil sin verificar; si no, al correo vigente de la cuenta. Responde `204` sin cuerpo. El root no puede usarlo.

- Reenviar invalida todos los enlaces vigentes anteriores de la cuenta.
- Si el correo ya está verificado y no hay un cambio pendiente, no hay nada que reenviar.
- Si el correo no se puede enviar, el enlace queda creado igual y el fallo se anota en el log; el cliente puede volver a pedirlo.
- El enlace tiene la misma vigencia de 24 horas y también es de un solo uso.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `correo_ya_verificado` | El correo ya está verificado (o la cuenta no tiene correo). |
| 401 | `no_autenticado` | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | El rol no es cliente ni administrador. |

## Perfil

### `GET /api/v1/usuarios/me/perfil`

Con sesión de cliente o administrador. Devuelve `200 PerfilSalida`:

```json
{
  "id": 12,
  "nombre_usuario": "lauragomez",
  "rol": "cliente",
  "tipo_documento": "CC",
  "numero_documento": "1088345921",
  "nombres": "Laura",
  "apellidos": "Gómez Ríos",
  "fecha_nacimiento": "1995-03-14",
  "lugar_nacimiento": "Pereira, Risaralda",
  "direccion_facturacion": "Cra. 7 # 19-28, Pereira",
  "genero": "femenino",
  "email": "laura.gomez@correo.co",
  "email_verificado": true,
  "email_pendiente": null,
  "telefono": "310 555 0192",
  "imagen_url": null,
  "suscrito_noticias": false
}
```

- El root no tiene perfil (`403 sin_permiso`).
- `email` es el correo vigente de la cuenta; `email_pendiente` es el correo nuevo que espera verificación (HU-07).
- `imagen_url` es `null` sin imagen y `suscrito_noticias` es `false` para un administrador.
- Un administrador que todavía no completó su registro (HU-12) no tiene perfil: `404 no_encontrado`.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 401 | `no_autenticado` | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | El rol es root. |
| 404 | `no_encontrado` | La cuenta aún no tiene sus datos personales. |

### `PUT /api/v1/usuarios/me/perfil`

Con sesión de cliente o administrador. Actualiza los datos editables y devuelve `200 PerfilSalida` con el perfil ya guardado. Entrada (`PerfilEntrada`):

```json
{
  "nombres": "Laura",
  "apellidos": "Gómez Ríos",
  "fecha_nacimiento": "1995-03-14",
  "lugar_nacimiento": "Pereira, Risaralda",
  "direccion_facturacion": "Cra. 7 # 19-28, Pereira",
  "genero": "femenino",
  "email": "laura.gomez@correo.co",
  "telefono": "310 555 0192"
}
```

- `tipo_documento`, `numero_documento` y `nombre_usuario` identifican la cuenta y no se editan: no hacen parte de `PerfilEntrada` y el servidor los ignora si llegan.
- `fecha_nacimiento` no puede ser futura.
- Un correo distinto del vigente queda en `email_pendiente` y se envía el enlace de HU-02 al correo nuevo; `email` sigue siendo el de la cuenta hasta verificarlo (SUP-42).
- Un correo que ya usa otra cuenta del mismo rol, o que otra cuenta del mismo rol tiene pendiente, se rechaza con `409 datos_duplicados` en `campos.email`.
- Guardar de nuevo el correo pendiente actualiza el resto de los datos sin enviar otro enlace; para pedir uno nuevo se usa `POST /usuarios/me/verificacion/reenviar`. Volver a escribir el correo vigente descarta el pendiente.
- Un `email_verificado` que ya era `true` sigue siéndolo mientras el correo nuevo esté pendiente.

| HTTP | `codigo` | `campos` | Cuándo |
|---|---|---|---|
| 409 | `datos_duplicados` | `email` | El correo pertenece a otra cuenta del mismo rol. |
| 422 | `datos_invalidos` | `fecha_nacimiento` | La fecha es futura. |
| 422 | `datos_invalidos` | otro campo | Formato inválido (`email`, `telefono`, `genero`, etc.). |
| 401 | `no_autenticado` | | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | | El rol es root. |
| 404 | `no_encontrado` | | La cuenta aún no tiene sus datos personales. |

## Imagen de perfil

Con sesión de cliente o administrador. La imagen se sube después del registro (HU-01) y se
administra desde el perfil (HU-07, RF-03 y RF-08). El tipo se decide por el contenido del
archivo, no por su extensión: solo se aceptan JPG o PNG de máximo 2 MB. El archivo se guarda
fuera del código, en el volumen `archivos` (`ARCHIVOS_DIR`), y sobrevive a `docker compose down`.

### `PUT /api/v1/usuarios/me/imagen`

`multipart/form-data` con el campo `imagen`. Sube o reemplaza la imagen y devuelve
`200 PerfilSalida` con el `imagen_url` nuevo.

```bash
curl -X PUT http://localhost:8000/api/v1/usuarios/me/imagen \
  -H "Cookie: sta_sesion=…" -F "imagen=@laura.png"
```

- `imagen_url` cambia en cada subida (`/api/v1/usuarios/me/imagen?v=1`, `?v=2`, …) para que el
  navegador no muestre la anterior desde su caché.
- Si la subida reemplaza una imagen anterior, el archivo viejo se sobrescribe.

| HTTP | `codigo` | `campos` | Cuándo |
|---|---|---|---|
| 422 | `datos_invalidos` | `imagen` | No es JPG ni PNG, está vacía, o pesa más de 2 MB. |
| 401 | `no_autenticado` | | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | | El rol es root. |
| 404 | `no_encontrado` | | La cuenta aún no tiene sus datos personales. |

### `GET /api/v1/usuarios/me/imagen`

Devuelve `200` con la imagen (`Content-Type: image/png` o `image/jpeg`). Es la URL que trae
`imagen_url` en el perfil.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | La cuenta no tiene imagen. |
| 401 | `no_autenticado` | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | El rol es root. |

### `DELETE /api/v1/usuarios/me/imagen`

Quita la imagen y responde `204` sin cuerpo. Es idempotente: sin imagen también responde `204`.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 401 | `no_autenticado` | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | El rol es root. |

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
  "email_verificado": true,
  "registro_completo": true,
  "nombres": "Laura",
  "apellidos": "Gómez Ríos"
}
```

`rol` es `root`, `admin` o `cliente`. El root no tiene correo (`email: null`, RF-01). `registro_completo` es `false` para un administrador que todavía no completó su registro (HU-12); `nombres` y `apellidos` son `null` para el root y para ese administrador.

Tras 5 intentos fallidos consecutivos la cuenta se bloquea 15 minutos (RNF-13). Durante el bloqueo, cualquier intento, incluso con la contraseña correcta, responde `429`; el encabezado `Retry-After` lleva los segundos que faltan. Un login correcto reinicia el contador, y al vencer el bloqueo el contador vuelve a cero.

| HTTP | `codigo` | `mensaje` | Cuándo |
|---|---|---|---|
| 401 | `credenciales_invalidas` | Usuario o contraseña incorrectos. | Usuario inexistente o contraseña errada: el mensaje no dice cuál (RF-06). |
| 403 | `cuenta_inactiva` | Cuenta inactiva. | Credenciales correctas de una cuenta desactivada (RF-02, RF-10). |
| 422 | `datos_invalidos` | Revisa los campos marcados. | Falta `usuario` o `contrasena`. |
| 429 | `demasiados_intentos` | Cuenta bloqueada. Intenta de nuevo en 15 minutos. | 5 intentos fallidos consecutivos. `Retry-After` indica los segundos restantes (RNF-13). |

### `POST /api/v1/auth/logout`

Con o sin sesión. Invalida la sesión en el servidor y borra la cookie. Responde `204` sin cuerpo.

### `GET /api/v1/auth/me`

Con sesión de cualquier rol. Devuelve el usuario de la sesión, con el mismo cuerpo que el login.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 401 | `no_autenticado` | Sin cookie, token alterado, sesión vencida o cerrada, o cuenta desactivada. |

## Contraseña

### `POST /api/v1/auth/restablecimiento`

Sin sesión. Envía al correo un enlace de un solo uso, válido 30 minutos, para definir una contraseña nueva (HU-05, RF-07). Sirve para clientes y administradores; el root nunca recibe enlace porque cambia su contraseña desde su sesión (HU-06).

Entrada:

```json
{ "email": "laura.gomez@correo.co" }
```

`202`: siempre responde lo mismo, exista o no el correo, para no revelar qué correos están registrados.

```json
{ "mensaje": "Si el correo está registrado, recibirás un enlace válido por 30 minutos." }
```

- El enlace lleva al frontend (`/restablecer-contrasena?token=…`) y no exige sesión: se puede abrir en otro dispositivo.
- Si el correo pertenece a una cuenta de cliente y a una de administrador (SUP-18), se envía un enlace por cada cuenta. El correo identifica el nombre de usuario y el tipo de cuenta para que el titular los distinga.
- Solo se envían enlaces a cuentas activas. Al pedir uno nuevo, los enlaces anteriores sin usar dejan de servir.
- Si el correo no se puede enviar, la solicitud responde igual y el fallo queda en el log sin exponer el correo.

| HTTP | `codigo` | `campos` | Cuándo |
|---|---|---|---|
| 422 | `datos_invalidos` | `email` | Falta el correo o no tiene un formato válido. |

### `POST /api/v1/auth/restablecimiento/confirmar`

Sin sesión. Define la contraseña nueva con el token del enlace (HU-05, RF-07). Responde `204` sin cuerpo.

Entrada:

```json
{ "token": "…", "contrasena_nueva": "OtraClave99", "confirmacion": "OtraClave99" }
```

- El token es de un solo uso y vence en 30 minutos (SUP-19). Un enlace vencido, ya usado o de una cuenta desactivada responde `400 enlace_invalido`.
- El token se valida antes que la contraseña: un enlace inválido siempre responde `enlace_invalido`.
- La contraseña nueva cumple RNF-08: mínimo 8 caracteres, al menos una letra y un número. Se guarda como hash Argon2id, nunca en texto plano.
- Al confirmar, la contraseña anterior deja de funcionar y se cierran todas las sesiones abiertas de esa cuenta. La cookie no se borra del navegador, pero el servidor la rechaza en la siguiente petición. En ningún caso se muestra ni se envía la contraseña actual.

| HTTP | `codigo` | `campos` | Cuándo |
|---|---|---|---|
| 400 | `enlace_invalido` | | Token inexistente, vencido, ya usado o de una cuenta desactivada. |
| 422 | `datos_invalidos` | `contrasena_nueva` | No cumple la política de RNF-08. |
| 422 | `datos_invalidos` | `confirmacion` | No coincide con la contraseña nueva. |

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

## Desactivación de cuenta

### `GET /api/v1/usuarios/me/desactivacion`

Con sesión de cliente. Indica si la cuenta se puede desactivar y, si no, qué compras o reservas
activas en vuelos futuros lo impiden (HU-09, RF-10). La pantalla del perfil muestra el aviso y
deshabilita el botón antes de intentarlo.

```json
{
  "puede_desactivar": false,
  "bloqueos": [
    {
      "tipo": "compra",
      "codigo_reserva": "K7Q2MX",
      "vuelo_id": 88,
      "vuelo_codigo": "STA-00088",
      "origen": "Bogotá",
      "destino": "Madrid",
      "salida": "2026-12-11T03:00:00Z"
    }
  ]
}
```

- `tipo` es `compra` o `reserva`; `codigo_reserva` es `null` en una reserva.
- `salida` va en ISO 8601 y UTC (RF-15).
- Los bloqueos salen de `reservas.tiquetes_activos_futuros_de_cliente`. En la iteración 1
  todavía no hay ventas, así que la lista siempre sale vacía.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 401 | `no_autenticado` | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | El rol no es cliente. |

### `POST /api/v1/usuarios/me/desactivacion`

Con sesión de cliente. Desactiva la cuenta y responde `204` sin cuerpo; la respuesta borra la
cookie de sesión.

- Es un borrado lógico (RF-10): la fila de `usuarios` queda con `activo: false` y se conservan
  los datos personales, el histórico, las preferencias y el saldo del monedero.
- Se cierran todas las sesiones abiertas de la cuenta y el siguiente inicio de sesión responde
  `403 cuenta_inactiva`.
- Antes de desactivar se consultan las compras y reservas activas en vuelos futuros; si hay
  alguna, no se cambia nada.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `tiquetes_activos` | Tiene compras o reservas activas en vuelos futuros: debe cancelarlas o esperar. |
| 401 | `no_autenticado` | Sin sesión o sesión vencida. |
| 403 | `sin_permiso` | El rol no es cliente. |

## Usuario root

`python -m app.seed` (lo corre el contenedor del backend al arrancar) crea el root con `ROOT_USERNAME` y `ROOT_PASSWORD` del `.env` si todavía no existe un usuario con rol root. Si ya existe, no lo modifica: el root cambia su contraseña desde su sesión (RF-01).
