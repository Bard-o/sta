# Contrato de la API · Iteración 1

HU-01 a HU-19: usuarios, administración de vuelos y noticias. Este archivo es el contrato acordado antes de implementar: los `schemas.py` de cada módulo ya lo reflejan y la documentación interactiva (http://localhost:8000/docs) lo muestra completo.

Las convenciones generales (prefijo, `snake_case`, UTC, COP, cookie de sesión, formato único de error) están en [`README.md`](README.md) y no se repiten aquí.

## Estado

- Cada endpoint de este archivo existe en el backend como **stub**: valida la sesión, el rol y el cuerpo, y responde `501 no_implementado`. El issue de cada HU reemplaza el stub por la implementación sin cambiar la firma.
- Ya implementados: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` y `POST /usuarios/registro` (ver [`usuarios.md`](usuarios.md)).
- El frontend puede avanzar sin esperar al backend con la API simulada (MSW); ver [Mocks para el frontend](#mocks-para-el-frontend).

## Convenciones de este contrato

**Roles.** *Público*: sin sesión (visitante) o con cualquier rol. *Sesión*: cualquier rol autenticado. *Cliente*, *Admin*, *Root*: solo ese rol. Sin sesión, un endpoint protegido responde `401 no_autenticado`; con otro rol, `403 sin_permiso` (RF-11, RNF-10). Los tests `test_permisos.py` de cada módulo recorren esta matriz.

**Paginación.** Los listados paginados reciben `pagina` (desde 1) y `por_pagina` (por defecto 20, máximo 100; noticias: 10 y 50) y responden:

```json
{ "items": [], "total": 0, "pagina": 1, "por_pagina": 20 }
```

**Horas.** Toda fecha y hora de salida es UTC en ISO 8601 (`2026-12-11T03:00:00Z`) y cada ciudad trae su `zona_horaria` IANA para mostrar la hora local con su desfase (IU-05, RF-15). Hay una sola excepción: al programar o editar un vuelo, el administrador escribe `fecha_salida` y `hora_salida` **locales del origen y sin desfase**, que es lo que pide el formulario (RF-13); el backend las convierte a UTC con tzdata, incluido el horario de verano.

**Validación.** El tipo, el formato y los rangos de cada campo los valida Pydantic y devuelven `422 datos_invalidos` con `campos`. Las reglas de negocio (fecha futura, política de contraseña, ruta permitida, unicidad…) las valida `service.py` y responden con el código de cada tabla. En ambos casos el error de un campo va en `campos` con la misma clave del cuerpo (IU-07).

### Errores comunes

Además de los de [`README.md`](README.md):

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 403 | `registro_incompleto` | Un administrador sin registro completo llama a cualquier endpoint que no sea `/auth/*` ni `POST /administradores/me/registro` (HU-12). |
| 403 | `correo_no_verificado` | Un cliente con el correo sin verificar intenta suscribirse (HU-08). En la iteración 2 aplica también a reservar y comprar (HU-02). |
| 400 | `enlace_invalido` | El token de un enlace de correo no existe, venció o ya se usó (HU-02, HU-05, HU-08). |
| 409 | `datos_duplicados` | Un dato único ya pertenece a otra cuenta; `campos` dice cuál (RF-04). |
| 501 | `no_implementado` | El endpoint todavía es un stub. |

## Endpoints por historia

### Módulo usuarios · dueño: Backend A

#### HU-01 Registrarse como cliente

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/usuarios/registro` | Visitante | `201 UsuarioSalida` + cookie de sesión |
| PUT | `/api/v1/usuarios/me/imagen` | Cliente, Admin | `200 PerfilSalida` |

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

- `tipo_documento`: `CC`, `TI`, `RC`, `CE` o `PA` (pasaporte). `numero_documento`: alfanumérico, 3 a 20 caracteres, sin espacios ni puntos. `genero`: `femenino`, `masculino` u `otro`. `telefono` es opcional. `nombre_usuario`: 3 a 50 caracteres entre letras, números, `.`, `_` y `-`.
- La imagen de perfil (opcional, JPG o PNG de 2 MB como máximo) se sube después del registro, ya con la sesión iniciada: `PUT /usuarios/me/imagen` en `multipart/form-data` con el campo `imagen`.

Reglas:

- `acepta_politica` debe ser `true`; se guarda la fecha de aceptación (Ley 1581 de 2012).
- `fecha_nacimiento` no puede ser futura. No hay edad mínima de registro.
- `contrasena`: 8 caracteres o más, con al menos una letra y un número (RNF-08); se guarda con Argon2id.
- `nombre_usuario` es único en todo el sistema (sin distinguir mayúsculas). El documento (tipo y número) y el correo son únicos entre las cuentas de cliente (RF-04, SUP-18). El correo se guarda en minúscula.
- La cuenta nace con `email_verificado: false`, el monedero en $ 0 (SUP-39; el monedero llega en la iteración 2) y sin suscripción a noticias. Se envía el enlace de verificación (HU-02) y se inicia la sesión.
- Con una sesión abierta, el registro responde `403 sin_permiso` (solo el visitante se registra, Apéndice B).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `datos_duplicados` | `campos` con `nombre_usuario`, `numero_documento` o `email`. |
| 422 | `datos_invalidos` | `campos` con `acepta_politica`, `fecha_nacimiento`, `email`, `contrasena` o el campo con formato inválido. Imagen que no es JPG o PNG o pesa más de 2 MB: `campos.imagen`. |

#### HU-02 Verificar correo electrónico

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/usuarios/verificacion` | Público | `204` |
| POST | `/api/v1/usuarios/me/verificacion/reenviar` | Cliente, Admin | `204` |

- El enlace del correo lleva al frontend (`/verificar-correo?token=…`), que envía `{ "token": "…" }`. No exige sesión: el enlace se puede abrir en otro dispositivo.
- El token es de un solo uso y vale 24 horas (SUP-19). Reenviar invalida el anterior.
- Si el token corresponde a un cambio de correo (HU-07), el correo pendiente pasa a ser el de la cuenta.
- Mientras `email_verificado` sea `false`, el cliente no puede suscribirse a noticias (`403 correo_no_verificado`) ni, desde la iteración 2, reservar o comprar.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `enlace_invalido` | Token inexistente, vencido o ya usado. El frontend ofrece reenviar. |
| 409 | `correo_ya_verificado` | Reenviar sin un correo pendiente de verificar. |

#### HU-03 Iniciar sesión

`POST /api/v1/auth/login` (público), ya implementado; contrato en [`usuarios.md`](usuarios.md). Lo que agrega esta iteración:

- `UsuarioSalida` trae tres campos nuevos: `registro_completo` (false para un administrador que no ha completado HU-12), `nombres` y `apellidos` (null para el root y para el administrador con el registro incompleto). El frontend decide con ellos a dónde llevar al usuario y qué nombre mostrar en el menú.
- Bloqueo por intentos (RNF-13): tras 5 intentos fallidos consecutivos, la cuenta queda bloqueada 15 minutos; el sexto intento responde `429 demasiados_intentos` aunque la contraseña sea correcta, con el encabezado `Retry-After` en segundos y el tiempo de espera en `mensaje`.

```json
{
  "id": 3,
  "nombre_usuario": "cruiz",
  "email": "carlos.ruiz@avianco.test",
  "rol": "admin",
  "email_verificado": true,
  "registro_completo": true,
  "nombres": "Carlos",
  "apellidos": "Ruiz"
}
```

#### HU-04 Cerrar sesión

`POST /api/v1/auth/logout`, ya implementado: invalida la sesión en el servidor y responde `204`.

#### HU-05 Restablecer contraseña

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/auth/restablecimiento` | Público | `202 MensajeSalida` |
| POST | `/api/v1/auth/restablecimiento/confirmar` | Público | `204` |

```json
{ "email": "laura.gomez@correo.co" }
```

```json
{ "mensaje": "Si el correo está registrado, recibirás un enlace válido por 30 minutos." }
```

```json
{ "token": "…", "contrasena_nueva": "OtraClave99", "confirmacion": "OtraClave99" }
```

- La primera respuesta es idéntica exista o no el correo (RF-07). Si el correo pertenece a una cuenta de cliente y a una de administrador (SUP-18), se envía un enlace por cada cuenta.
- El root no tiene correo, así que nunca recibe enlace (cambia su contraseña con HU-06).
- El enlace lleva al frontend (`/restablecer-contrasena?token=…`); es de un solo uso y vale 30 minutos.
- Al confirmar: la contraseña nueva cumple RNF-08, la anterior deja de funcionar y se cierran todas las sesiones del usuario. Nunca se muestra ni se envía la contraseña actual.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `enlace_invalido` | Token inexistente, vencido o ya usado. |
| 422 | `datos_invalidos` | `campos.contrasena_nueva` (política) o `campos.confirmacion` (no coincide). |

#### HU-06 Cambiar contraseña

`PUT /api/v1/usuarios/me/contrasena` · Sesión (cliente, admin o root) · `204`.

```json
{ "contrasena_actual": "Clave1234", "contrasena_nueva": "OtraClave99", "confirmacion": "OtraClave99" }
```

- Es la única forma en que el root cambia su contraseña (RF-01). La sesión actual sigue abierta.
- Si la contraseña actual es incorrecta, no se cambia nada.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 422 | `contrasena_actual_incorrecta` | `campos.contrasena_actual`. |
| 422 | `datos_invalidos` | `campos.contrasena_nueva` (política) o `campos.confirmacion` (no coincide). |

#### HU-07 Editar perfil

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/usuarios/me/perfil` | Cliente, Admin | `200 PerfilSalida` |
| PUT | `/api/v1/usuarios/me/perfil` | Cliente, Admin | `200 PerfilSalida` |
| PUT | `/api/v1/usuarios/me/imagen` | Cliente, Admin | `200 PerfilSalida` |
| GET | `/api/v1/usuarios/me/imagen` | Cliente, Admin | `200` imagen PNG o JPEG |
| DELETE | `/api/v1/usuarios/me/imagen` | Cliente, Admin | `204` |

`PerfilEntrada`: los campos de `RegistroClienteEntrada` **sin** `tipo_documento`, `numero_documento`, `nombre_usuario`, `contrasena` ni `acepta_politica`, que identifican la cuenta o tienen su propio endpoint.

`PerfilSalida`:

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
  "email_pendiente": "laura.g@nuevo.co",
  "telefono": "310 555 0192",
  "imagen_url": "/api/v1/usuarios/me/imagen?v=3",
  "suscrito_noticias": true
}
```

- El root no tiene perfil (`403 sin_permiso`).
- Un correo distinto no reemplaza al actual: queda en `email_pendiente`, se le envía el enlace de HU-02 y `email` sigue siendo el de la cuenta hasta verificarlo (SUP-42). Un correo que ya usa otra cuenta del mismo rol se rechaza.
- `imagen_url` cambia cada vez que se sube una imagen, para que el navegador no muestre la anterior desde su caché.
- Los datos nuevos se usarán en el autocompletado de viajeros (iteración 2); los tiquetes ya emitidos no cambian (RF-08).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `datos_duplicados` | `campos.email`. |
| 422 | `datos_invalidos` | `campos.fecha_nacimiento` futura, formato inválido o `campos.imagen`. |
| 404 | `no_encontrado` | `GET /me/imagen` sin imagen. |

#### HU-08 Suscribirse a noticias

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| PUT | `/api/v1/usuarios/me/suscripcion` | Cliente | `200 SuscripcionSalida` |
| POST | `/api/v1/usuarios/suscripcion/baja` | Público | `204` |

```json
{ "noticias": true }
```

- Solo se suscribe un cliente con el correo verificado. Darse de baja (`false`) siempre se permite.
- El correo de cada noticia trae un enlace de baja (`/noticias/baja?token=…` en el frontend) que funciona sin iniciar sesión: el frontend envía `{ "token": "…" }`. Ese token identifica la suscripción y no vence.
- El cambio aplica desde el siguiente envío (RF-09).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 403 | `correo_no_verificado` | Suscribirse sin el correo verificado. El frontend ofrece reenviar la verificación. |
| 400 | `enlace_invalido` | Token de baja inexistente. |

#### HU-09 Desactivar cuenta

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/usuarios/me/desactivacion` | Cliente | `200 DesactivacionSalida` |
| POST | `/api/v1/usuarios/me/desactivacion` | Cliente | `204` y borra la cookie |

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

- El `GET` permite mostrar el aviso y deshabilitar el botón antes de intentarlo. Los bloqueos salen de `reservas.tiquetes_activos_futuros_de_cliente` (vacío hasta la iteración 2).
- Es un borrado lógico (RF-10): datos, histórico, preferencias y saldo se conservan; la cuenta queda inactiva, se cierran todas sus sesiones y el siguiente login responde `cuenta_inactiva`.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `tiquetes_activos` | Hay compras o reservas activas en vuelos futuros. |

#### HU-10 Crear administrador

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/administradores` | Root | `200 AdministradorSalida[]` |
| POST | `/api/v1/administradores` | Root | `201 AdministradorSalida` |

```json
{ "nombre_usuario": "jtorres", "contrasena_temporal": "Temporal123" }
```

```json
{
  "id": 5,
  "nombre_usuario": "jtorres",
  "nombres": null,
  "apellidos": null,
  "estado": "registro_incompleto",
  "creado_en": "2026-09-29T21:40:00Z"
}
```

- `estado`: `activo`, `inactivo` o `registro_incompleto`. El listado va del más reciente al más antiguo.
- `nombre_usuario` único en todo el sistema; la contraseña temporal cumple RNF-08.
- No existe ningún endpoint para crear un root (RF-01).
- Se audita: `auditoria.registrar(accion="administrador.crear", …)`, sin la contraseña.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `datos_duplicados` | `campos.nombre_usuario`. |
| 422 | `datos_invalidos` | `campos.contrasena_temporal` (política) o formato del nombre de usuario. |

#### HU-11 Desactivar o reactivar administrador

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/administradores/{admin_id}/desactivar` | Root | `200 AdministradorSalida` |
| POST | `/api/v1/administradores/{admin_id}/reactivar` | Root | `200 AdministradorSalida` |

- Borrado lógico. Desactivar cierra todas las sesiones del administrador; su siguiente login responde `cuenta_inactiva`.
- Reactivar devuelve el estado anterior: `activo` o `registro_incompleto`.
- Se audita cada cambio (`administrador.desactivar`, `administrador.reactivar`) con el estado anterior y el nuevo.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | El id no es de un administrador. |
| 409 | `estado_invalido` | Desactivar uno inactivo o reactivar uno activo. |

#### HU-12 Completar registro de administrador

`POST /api/v1/administradores/me/registro` · Admin con el registro incompleto · `200 UsuarioSalida` (con `registro_completo: true`).

Entrada (`RegistroAdministradorEntrada`): los datos personales de HU-01 (sin `nombre_usuario`, `contrasena` ni `acepta_politica`) más el cambio de contraseña:

```json
{
  "tipo_documento": "CC",
  "numero_documento": "10234567",
  "nombres": "Jorge",
  "apellidos": "Torres",
  "fecha_nacimiento": "1990-05-02",
  "lugar_nacimiento": "Cali, Valle del Cauca",
  "direccion_facturacion": "Cl. 5 # 38-14, Cali",
  "genero": "masculino",
  "email": "jorge.torres@avianco.test",
  "telefono": null,
  "contrasena_temporal": "Temporal123",
  "contrasena_nueva": "MiClave2026",
  "confirmacion": "MiClave2026"
}
```

- Mientras el registro esté incompleto, cualquier otro endpoint responde `403 registro_incompleto` (lo aplica `core`, ver [Pendientes de infraestructura](#pendientes-de-infraestructura)).
- El documento y el correo son únicos entre administradores; la misma persona puede tener además una cuenta de cliente (RF-04).
- La contraseña temporal deja de funcionar. La sesión actual sigue abierta.
- El correo del administrador no pasa por la verificación de HU-02 en esta iteración: queda `email_verificado: true`.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `registro_ya_completo` | El administrador ya completó su registro. |
| 409 | `datos_duplicados` | `campos.numero_documento` o `campos.email` entre administradores. |
| 422 | `contrasena_actual_incorrecta` | `campos.contrasena_temporal`. |
| 422 | `datos_invalidos` | Política de contraseña, confirmación o datos personales. |

### Módulo vuelos · dueño: Backend B

#### Tipos del módulo

`Vuelo`, la base de todas las respuestas:

```json
{
  "id": 88,
  "codigo": "STA-00088",
  "tipo": "internacional",
  "origen": { "codigo": "BOG", "nombre": "Bogotá", "zona_horaria": "America/Bogota" },
  "destino": { "codigo": "MAD", "nombre": "Madrid", "zona_horaria": "Europe/Madrid" },
  "salida": "2026-12-11T03:00:00Z",
  "llegada": "2026-12-11T13:00:00Z",
  "duracion_minutos": 600,
  "precio_economica": 2450000,
  "precio_primera": 6900000,
  "capacidad": { "primera": 50, "economica": 200, "total": 250 },
  "estado": "programado"
}
```

- `estado`: `programado`, `realizado` o `cancelado`. `precio_*` es el precio base; el vigente con promoción está en `VueloDetalle`.
- `VueloAdmin` = `Vuelo` + `ocupacion` (por clase: `capacidad`, `vendidas`, `reservadas`, `disponibles`), `reservas_activas`, `tiquetes_vendidos`, `editable`, `motivo_no_editable`, `cancelable` y `promociones` (vigentes y programadas). Es lo que necesitan la tabla de vuelos programados (S09) y el diálogo de cancelación.
- Clases: `economica` y `primera`. Días: `lun`, `mar`, `mie`, `jue`, `vie`, `sab`, `dom`.

#### HU-13 Programar vuelo

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/ciudades` | Público | `200 Ciudad[]` |
| POST | `/api/v1/vuelos/vista-previa` | Admin | `200 VueloVistaPrevia` |
| POST | `/api/v1/vuelos` | Admin | `201 VueloAdmin` |

`Ciudad`:

```json
{
  "codigo": "PEI",
  "nombre": "Pereira",
  "pais": "Colombia",
  "zona_horaria": "America/Bogota",
  "tipo": "nacional",
  "habilitada_internacional": true,
  "imagen_url": "/imagenes/ciudades/PEI.jpg"
}
```

`VueloEntrada` (también para editar):

```json
{
  "origen": "BOG",
  "destino": "MAD",
  "fecha_salida": "2026-12-10",
  "hora_salida": "22:00",
  "duracion_minutos": 600,
  "precio_economica": 2450000,
  "precio_primera": 6900000
}
```

- El catálogo (RF-12) son las 32 capitales departamentales, Madrid, Londres, Nueva York, Buenos Aires y Miami, con su código de aeropuerto y su zona IANA. Todas las ciudades colombianas usan `America/Bogota` (SUP-32).
- La vista previa aplica las mismas validaciones que guardar y devuelve tipo, capacidad, salida y llegada sin guardar nada (el recuadro «Así lo verá el cliente» de S08).
- Validaciones (RF-13, RF-14, RF-16): ciudades del catálogo; origen distinto del destino; ruta permitida (nacional entre capitales, o internacional entre Pereira, Bogotá, Medellín, Cali o Cartagena y un destino internacional, en ambos sentidos); salida futura; `duracion_minutos` entre 1 y 1439; precios enteros mayores que 0; ningún otro vuelo programado con el mismo origen, destino y salida.
- El sistema calcula `tipo`, la capacidad (nacional 25 + 125; internacional 50 + 200), `salida` en UTC y `llegada` = salida + duración (RF-15). El código `STA-nnnnn` sale de una secuencia y nunca se reutiliza (SUP-01).
- En la misma transacción: `noticias.publicar_noticia_vuelo(...)` (RF-22) y `auditoria.registrar(accion="vuelo.crear", …)`.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 422 | `ruta_no_permitida` | `campos.destino`. Ej.: Manizales → Miami, Madrid → Londres. |
| 422 | `datos_invalidos` | Ciudad fuera del catálogo, origen igual al destino (`campos.destino`), salida pasada (`campos.fecha_salida`), duración o precios fuera de rango. |
| 409 | `vuelo_duplicado` | `campos.hora_salida`: ya existe un vuelo de esa ruta a esa hora. |

#### HU-14 Programar vuelos recurrentes

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/vuelos/recurrentes/vista-previa` | Admin | `200 SerieVistaPrevia` |
| POST | `/api/v1/vuelos/recurrentes` | Admin | `201 SerieVuelosSalida` |

```json
{
  "origen": "PEI",
  "destino": "BOG",
  "hora_salida": "06:00",
  "duracion_minutos": 50,
  "precio_economica": 280000,
  "precio_primera": 750000,
  "dias_semana": ["lun"],
  "desde": "2026-10-01",
  "hasta": "2026-12-31"
}
```

```json
{
  "creados": [{ "id": 93, "codigo": "STA-00093", "…": "Vuelo" }],
  "omitidas": [
    { "fecha": "2026-10-05", "codigo": "salida_en_pasado", "motivo": "La salida ya pasó." },
    { "fecha": "2026-12-07", "codigo": "vuelo_duplicado", "motivo": "Ya existe un vuelo igual." }
  ]
}
```

- Los 7 días equivalen a «diario». Se genera una fecha por cada día del periodo (ambos extremos incluidos) que cae en `dias_semana`.
- `hasta` no puede ser anterior a `desde` ni estar a más de 12 meses de hoy (SUP-37).
- Cada ocurrencia es un vuelo independiente, con su código, su noticia y su registro de auditoría; editarla o cancelarla no afecta a las demás.
- Las fechas que chocan con un vuelo existente (RF-16) o cuya salida ya pasó se omiten y se informan; no son un error. Las demás validaciones de HU-13 sí rechazan toda la serie.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 422 | `datos_invalidos` | `campos.hasta` (periodo invertido o de más de 12 meses), `campos.dias_semana` vacío y los de HU-13. |
| 422 | `ruta_no_permitida` | Igual que HU-13. |

#### HU-15 Editar vuelo

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/vuelos` | Admin | `200 PaginaVuelosAdmin` |
| GET | `/api/v1/vuelos/{vuelo_id}/gestion` | Admin | `200 VueloAdmin` |
| PUT | `/api/v1/vuelos/{vuelo_id}` | Admin | `200 VueloAdmin` |

- Filtros de `GET /vuelos`: `estado` (por defecto `programado`), `desde` y `hasta` (fechas en hora de Colombia: salida para programados y cancelados, llegada para realizados), `q` (código o nombre de ciudad), `pagina`, `por_pagina`. Los programados van por salida ascendente; los realizados y cancelados, del más reciente al más antiguo.
- `PUT` recibe `VueloEntrada` completo y vuelve a aplicar todas las validaciones de HU-13, excluyendo al propio vuelo de la unicidad. Recalcula tipo, capacidad y llegada; el código se conserva.
- Solo se edita un vuelo `programado`, que no ha salido y que no tiene compras ni reservas vigentes (`editable: true`). Si la única reserva vence o se cancela, vuelve a ser editable.
- En la misma transacción: `noticias.actualizar_noticias_de_vuelo(...)` y `auditoria.registrar(accion="vuelo.editar", antes=…, despues=…)` con los valores anteriores y nuevos de los campos que cambiaron.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | El vuelo no existe. |
| 409 | `vuelo_con_reservas` | Tiene al menos una reserva vigente o una compra. |
| 409 | `vuelo_cerrado` | Ya salió, se realizó o está cancelado. |
| 409 / 422 | | Los de HU-13. |

#### HU-16 Cancelar vuelo sin ventas

`POST /api/v1/vuelos/{vuelo_id}/cancelar` · Admin · `200 CancelacionVueloSalida`.

```json
{ "vuelo": { "…": "VueloAdmin", "estado": "cancelado" }, "reservas_anuladas": 2 }
```

- Antes de confirmar, el frontend muestra `reservas_activas` del `VueloAdmin` («Tiene 2 reservas activas…»).
- Solo se cancela un vuelo programado, que no ha salido y sin tiquetes vendidos (`cancelable: true`). Con tiquetes vendidos se requiere la cancelación por fuerza mayor (HU-32, iteración 3).
- En la misma transacción: `reservas.anular_reservas_de_vuelo(...)` (anula, libera sillas y encola el correo a cada cliente), las promociones vigentes o programadas del vuelo pasan a `cancelada`, `noticias.retirar_noticias_de_vuelo(...)` (sale de la búsqueda y del carrusel) y `auditoria.registrar(accion="vuelo.cancelar", …)`. El código no se reutiliza.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | |
| 409 | `vuelo_con_tiquetes` | Tiene tiquetes vendidos. |
| 409 | `vuelo_cerrado` | Ya salió, se realizó o ya estaba cancelado. |

#### HU-17 Crear promoción

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/vuelos/{vuelo_id}/promociones` | Admin | `201 Promocion` |
| GET | `/api/v1/promociones` | Admin | `200 PaginaPromociones` |

```json
{
  "porcentaje": 40,
  "clases": ["economica"],
  "inicio": "2026-10-15T10:00:00-05:00",
  "fin": "2026-10-15T12:00:00-05:00"
}
```

- `inicio` y `fin` llevan desfase horario (el frontend envía el de Colombia); se guardan en UTC. `porcentaje` entre 1 y 90 (SUP-38); `clases` con una o las dos (SUP-05).
- Reglas (RF-23): el vuelo está programado y no ha salido; `fin` es posterior a `inicio` y está en el futuro; si `inicio` ya pasó, la promoción queda vigente de inmediato. Cada clase tiene como máximo una promoción vigente o programada.
- Estados: `programada`, `vigente`, `vencida` (pasó `fin`), `agotada` (se vendió la última silla disponible de sus clases) y `cancelada` (se canceló el vuelo).
- Precio vigente = `floor(precio_base × (100 − porcentaje) / 100)`, en pesos enteros. Las reservas y compras anteriores conservan su precio (RF-24).
- `GET /promociones` filtra por `estado` y va de la más reciente a la más antigua.
- En la misma transacción: `noticias.publicar_noticia_promocion(...)` (RF-25) y `auditoria.registrar(accion="promocion.crear", …)`.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | |
| 409 | `vuelo_cerrado` | El vuelo ya salió, se realizó o está cancelado. |
| 409 | `promocion_duplicada` | `campos.clases`: ya hay una vigente o programada para esa clase. |
| 422 | `datos_invalidos` | `campos.fin`, `campos.porcentaje` o `campos.clases`. |

#### HU-18 Consultar vuelos realizados

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/vuelos?estado=realizado` | Admin | `200 PaginaVuelosAdmin` |
| GET | `/api/v1/vuelos/{vuelo_id}/pasajeros` | Admin | `200 PasajerosVueloSalida` |

```json
{
  "vuelo": { "…": "Vuelo" },
  "ocupacion": {
    "primera": { "capacidad": 25, "vendidas": 25, "reservadas": 0, "disponibles": 0 },
    "economica": { "capacidad": 125, "vendidas": 113, "reservadas": 0, "disponibles": 12 }
  },
  "pasajeros": [
    { "nombres": "Ana", "apellidos": "Pérez", "clase": "economica", "silla": "12C", "numero_silla": 58 }
  ]
}
```

- Un proceso automático pasa a `realizado` cada vuelo programado cuya llegada ya pasó, como máximo 2 minutos después, y también al arrancar el servidor si estuvo apagado (RF-21, RNF-18). Al hacerlo llama a `noticias.retirar_noticias_de_vuelo(...)`.
- Un vuelo realizado no se edita, no se cancela y no recibe promociones (`vuelo_cerrado`).
- `silla` es fila + letra según el Apéndice A del SRS; `numero_silla` es el número interno (SUP-26). Los pasajeros salen de `reservas.pasajeros_de_vuelo` (vacío hasta la iteración 2).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | |

### Módulo noticias · dueño: Backend B

#### HU-19 Consultar noticias y carrusel

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/noticias` | Público | `200 PaginaNoticias` |
| GET | `/api/v1/noticias/carrusel` | Público | `200 Noticia[]` |
| GET | `/api/v1/vuelos/{vuelo_id}` | Público | `200 VueloDetalle` (módulo vuelos) |

`Noticia` (el mismo tipo en el listado y en el carrusel):

```json
{
  "id": 8,
  "tipo": "promocion",
  "titulo": "Promoción del 30 % en Bogotá → Miami, económica",
  "publicada_en": "2026-10-18T14:12:00Z",
  "vigente": true,
  "vuelo_id": 76,
  "vuelo_codigo": "STA-00076",
  "origen": { "codigo": "BOG", "nombre": "Bogotá", "zona_horaria": "America/Bogota" },
  "destino": { "codigo": "MIA", "nombre": "Miami", "zona_horaria": "America/New_York" },
  "salida": "2026-10-29T04:30:00Z",
  "precio_economica": 1980000,
  "precio_primera": 4500000,
  "imagen_url": "/imagenes/ciudades/MIA.jpg",
  "promocion": {
    "porcentaje": 30,
    "clases": ["economica"],
    "inicio": "2026-10-18T13:00:00Z",
    "fin": "2026-10-27T04:59:00Z",
    "estado": "vigente",
    "precio_economica": 1386000,
    "precio_primera": null
  }
}
```

- Las noticias son solo automáticas (RF-55): no hay `POST`, `PUT`, `PATCH` ni `DELETE` sobre `/noticias` (responden `405`).
- `tipo`: `vuelo` (RF-22) o `promocion` (RF-25). `titulo` lo arma el backend; la fecha y la hora se formatean en el frontend con `salida` y la zona del origen.
- `vigente`: el vuelo sigue programado y, si es de promoción, la promoción está vigente. El listado incluye las no vigentes (de la más reciente a la más antigua) para que el frontend las muestre sin destacar.
- El carrusel trae como máximo 10 noticias vigentes: primero las de promoción y luego las de vuelos, de la más reciente a la más antigua. Cada vuelo aparece una sola vez: si tiene una promoción vigente, con ella (SUP-06, SUP-41).
- `vuelo_id` abre el detalle público del vuelo: `VueloDetalle` es `Vuelo` más `economica` y `primera`, cada una con `precio_base`, `precio_vigente`, `promocion`, `disponibles` y `agotada`. Responde para cualquier `estado`, y el frontend avisa si el vuelo ya no está programado.

## Funciones entre módulos

Cuando un módulo necesita a otro, llama a estas funciones públicas del `service.py` del dueño. Las firmas ya existen en el código; las de las iteraciones futuras devuelven el valor neutro de «todavía no hay datos». Ninguna hace commit: se ejecutan dentro de la transacción de quien llama, para que todo se aplique o nada (RNF-17).

### `noticias.service` · dueño: Backend B · la llama vuelos

| Función | Cuándo la llama vuelos |
|---|---|
| `publicar_noticia_vuelo(db, vuelo: VueloPublicado)` | Al programar un vuelo, también cada ocurrencia de una serie (HU-13, HU-14). Encola el correo a los suscritos (RF-56). |
| `publicar_noticia_promocion(db, promocion: PromocionPublicada)` | Al crear una promoción (HU-17). |
| `actualizar_noticias_de_vuelo(db, vuelo: VueloPublicado)` | Al editar un vuelo (HU-15). |
| `retirar_noticias_de_vuelo(db, vuelo_id)` | Al cancelar un vuelo o pasarlo a realizado (HU-16, HU-18). |
| `terminar_noticia_promocion(db, promocion_id, estado)` | Cuando una promoción se agota o se cancela antes de su `fin`. El vencimiento por fecha lo calcula noticias. |

`VueloPublicado` y `PromocionPublicada` son dataclasses de `noticias/service.py` con la copia de los datos que la noticia muestra (código, ciudades, salida, precios, imagen; porcentaje, clases y vigencia). Noticias no consulta a vuelos: vuelos le avisa de cada cambio, así la dependencia va en un solo sentido.

### `usuarios.service` · dueño: Backend A · la llama noticias

| Función | Para qué |
|---|---|
| `suscriptores_noticias(db) -> list[SuscriptorNoticias]` | Destinatarios del correo de cada noticia: clientes activos, con el correo verificado y suscritos. Cada uno trae `token_baja` para el enlace de baja (HU-08, RF-56). |

### `auditoria.service` · dueño: Backend B · la llaman usuarios y vuelos

| Función | Para qué |
|---|---|
| `registrar(db, *, usuario_id, accion, entidad, entidad_id, antes=None, despues=None)` | RF-26. `accion`: `vuelo.crear`, `vuelo.editar`, `vuelo.cancelar`, `promocion.crear`, `administrador.crear`, `administrador.desactivar`, `administrador.reactivar`. `antes` y `despues`, solo con valores serializables en JSON y nunca con contraseñas. |

La consulta de la auditoría (HU-50) llega en la iteración 4.

### `reservas.service` · dueño: Backend B · la llaman vuelos y usuarios

Hasta la iteración 2 no existen reservas ni compras: estas funciones ya responden «sin ventas», que es correcto mientras tanto, y las HU-22 a HU-27 les dan el comportamiento real sin cambiar la firma.

| Función | Quién y para qué |
|---|---|
| `ocupacion_de_vuelos(db, vuelo_ids) -> dict[int, OcupacionVuelo]` | vuelos: ocupación por clase, reservas vigentes y tiquetes vendidos de varios vuelos en una consulta (HU-15, HU-16, HU-18). |
| `anular_reservas_de_vuelo(db, vuelo_id) -> int` | vuelos: al cancelar (HU-16). Libera sillas y encola el correo de anulación. |
| `pasajeros_de_vuelo(db, vuelo_id) -> list[PasajeroVuelo]` | vuelos: pasajeros con clase y silla (HU-18). |
| `tiquetes_activos_futuros_de_cliente(db, usuario_id) -> list[TiqueteActivo]` | usuarios: bloqueos para desactivar la cuenta (HU-09). |

## Pendientes de infraestructura

Necesitan un issue del líder porque tocan `core/`, Docker o recursos compartidos:

1. **Registro incompleto en `core/auth.py`.** `require_role` debe responder `403 registro_incompleto` a un administrador sin registro completo (HU-12), salvo en `/auth/*` y `POST /administradores/me/registro`. Depende del campo que agregue usuarios en su modelo.
2. **Procesos programados.** Un planificador en el backend para pasar vuelos a realizado y vencer promociones como máximo 2 minutos después de su hora, que también procese al arrancar lo que venció con el servidor apagado (RF-21, RNF-18).
3. **Cola de correos.** `core/mail.py` envía de forma síncrona. Las noticias a los suscritos deben salir por una cola que reintente si SMTP falla (RNF-05, RNF-21).
4. **Archivos.** Dónde se guardan las imágenes de perfil (un volumen de Docker) y el banco de imágenes por ciudad (SUP-30), que el contrato sirve en `/imagenes/ciudades/<CODIGO>.jpg` desde `frontend/public/`. Las imágenes deben tener una licencia que permita usarlas en un repositorio público.

## Decisiones de este contrato

Puntos que el SRS y las HU dejan abiertos y que este contrato fija. Si alguno cambia, se cambia aquí, en el `schemas.py` y en los mocks:

- La entrada de un vuelo usa fecha y hora locales del origen sin desfase; todas las salidas son UTC.
- La duración viaja en minutos (`duracion_minutos`), no en horas y minutos por separado.
- `telefono` es opcional en el registro y en el perfil: aparece en el wireframe S05, pero no en HU-01.
- `genero` admite `femenino`, `masculino` y `otro`.
- El registro inicia la sesión del cliente nuevo (el wireframe S02 lo muestra con sesión).
- El correo del administrador no se verifica en HU-12.
- Cambiar la contraseña con HU-06 no cierra la sesión actual; restablecerla con HU-05 cierra todas.
- Las promociones tienen el estado `cancelada` además de los del SRS, y una promoción cuyo `inicio` ya pasó queda vigente de inmediato.
- El precio con descuento se redondea hacia abajo al peso.
- Las noticias de vuelos cancelados o realizados siguen en el listado como no vigentes; el carrusel muestra cada vuelo una sola vez.
- `GET /vuelos/{vuelo_id}` es público para cualquier estado del vuelo.
- `UsuarioSalida` cambia (contrato existente): agrega `registro_completo`, `nombres` y `apellidos`.

## Mocks para el frontend

`frontend/src/mocks/` simula toda la API de esta iteración con MSW. Los datos de ejemplo (`datos.ts`) están tipados con `src/api/schema.d.ts` y los handlers usan `openapi-msw`, así que `npm run typecheck` falla si el contrato cambia y los mocks quedan desactualizados. Simulan las reglas justas para ver cada estado de las pantallas: roles, errores de validación, vuelo duplicado, vuelo con reservas, promoción duplicada…

Para activarlos, pon `VITE_API_MOCK=true` en tu `.env` y reinicia el frontend:

```bash
docker compose up -d frontend
```

- Solo funcionan en desarrollo (`npm run dev`), nunca en el build de producción.
- Lo que crees o cambies dura hasta recargar la página; la sesión simulada sobrevive a la recarga.
- Las peticiones sin handler pasan al backend real.

Usuarios de prueba (contraseña de todos: `Clave1234`):

| Usuario | Para probar |
|---|---|
| `lauragomez` | Cliente verificado y suscrito; tiene una compra activa, así que no puede desactivar la cuenta. |
| `pedrorios` | Cliente con el correo sin verificar. |
| `cruiz` | Administrador. |
| `jtorres` | Administrador con el registro incompleto (HU-12). |
| `root` | Root. |
| `amejia` | Administrador inactivo: `cuenta_inactiva`. |
| `bloqueado` | Cualquier contraseña: `429 demasiados_intentos`. |

Otros valores que disparan errores: el token `vencido` en verificación, restablecimiento y baja (`enlace_invalido`); un vuelo Manizales → Miami (`ruta_no_permitida`); Bogotá → Madrid el 10/12/2026 a las 22:00 (`vuelo_duplicado`, choca con STA-00088); editar STA-00051 (`vuelo_con_reservas`); cancelar STA-00088 (`vuelo_con_tiquetes`); una promoción en primera para STA-00088 (`promocion_duplicada`).
