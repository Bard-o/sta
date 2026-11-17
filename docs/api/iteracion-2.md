# Contrato de la API · Iteración 2

HU-20 a HU-31: búsqueda de vuelos, carrito, reservas y compras, y monedero. Este archivo es el contrato acordado antes de implementar: los `schemas.py` de `busqueda`, `carrito`, `reservas` y `monedero` ya lo reflejan y la documentación interactiva (http://localhost:8000/docs) lo muestra completo.

Las convenciones generales (prefijo, `snake_case`, UTC, COP, cookie de sesión, formato único de error) están en [`README.md`](README.md) y las de la iteración 1 (roles, paginación, validación) en [`iteracion-1.md`](iteracion-1.md#convenciones-de-este-contrato). Aquí solo se agrega lo nuevo.

## Estado

- Cada endpoint de este archivo existe en el backend como **stub**: valida la sesión, el rol y el cuerpo, y responde `501 no_implementado`. El issue de cada HU reemplaza el stub por la implementación sin cambiar la firma. El docstring de cada endpoint y las `description` de los campos salen en `schema.d.ts`: si cambian, hay que correr `npm run gen:api`.
- Los módulos `busqueda`, `carrito` y `monedero` todavía no tienen `service.py` ni `models.py`: los dueños los crean en sus issues. `reservas` ya tiene sus modelos, las reglas de los viajeros y las funciones públicas de consulta (#138), y la asignación de sillas (#137): sus endpoints las usan tal como están en `main`. `vuelos.service.limite_de_venta` ya existe desde #112 (este issue).
- El frontend puede avanzar sin esperar al backend con la API simulada (MSW); ver [Mocks para el frontend](#mocks-para-el-frontend).

| Endpoints o funciones | Issue que los implementa |
|---|---|
| `vuelos.service.limite_de_venta` | #112 (ya existe) |
| `GET /busqueda/vuelos`, `GET /busqueda/regresos` | #125, sobre `vuelos.service.buscar_vuelos` y `regresos_de` (#120) |
| `GET /carrito`, `/carrito/selecciones/*`, `DELETE /carrito` | #126 |
| `POST /reservas` | #118; con dos tramos, #130 |
| `POST /compras`, `GET /compras/{compra_id}`, `POST /compras/{compra_id}/confirmar`, `DELETE /compras/{compra_id}` | #124; con dos tramos, #130 |
| `POST /reservas/{reserva_id}/pagar`, `GET /mis-viajes` | #131 |
| `/monedero/*` | #119, sobre los modelos y funciones de #115 |

## Convenciones de este contrato

**Roles.** Los de la iteración 1, más *Cliente verificado*: un cliente con `email_verificado: true`; si no lo es, responde `403 correo_no_verificado` (HU-02). La búsqueda es pública para todos los roles (Apéndice B). Carrito, reservas, compras y monedero son solo del cliente: sin sesión `401 no_autenticado`, con otro rol `403 sin_permiso` (RNF-10). Un cliente nunca ve ni toca lo de otro: un id ajeno responde `404 no_encontrado`, igual que uno que no existe.

**Límite de venta.** Un vuelo se reserva o se compra mientras esté `programado` y no haya llegado su límite de venta: 1 hora antes de la salida si es nacional y 3 horas si es internacional (SUP-07, RF-36). Es el mismo límite de cancelación de RF-43 y lo calcula `vuelos.service.limite_de_venta`. Pasado el límite, el vuelo sale de la búsqueda, el carrito lo marca y reservar o comprar responde `fuera_de_plazo`.

**Tramos.** Un trayecto único tiene un tramo y uno completo, dos: `tramos[0]` es la ida y `tramos[1]` el regreso (RF-40). El índice es el mismo en los cuerpos, en las respuestas y en `campos` (`tramos.1.vuelo_id`).

**Viajeros y clases.** La clase va por viajero y por tramo: `viajeros[i].clases[j]` es la clase del viajero `i` en `tramos[j]` (RF-33, HU-26). Los errores de un viajero van en `campos` con su índice: `viajeros.2.numero_documento`.

**Horas.** Como en la iteración 1, todo instante viaja en UTC y cada ciudad trae su `zona_horaria`. Los filtros de fecha y hora de la búsqueda son la excepción: se comparan con la salida en la **hora local del origen** de cada vuelo, que es lo que el cliente ve en el tablero (RF-27). Los filtros por fecha de Mis viajes y de los movimientos usan la fecha de Colombia.

**Dinero.** Enteros en COP. Los movimientos del monedero llevan signo: positivo en recargas y reembolsos y negativo en compras; el saldo es su suma (RF-48). El precio de un tiquete se congela al reservar o al iniciar la compra (RF-24).

**Estados efectivos.** Lo que vence se informa vencido a su hora, aunque el proceso automático todavía no haya corrido: una reserva `vigente` cuyo `vence_en` ya pasó se devuelve `vencida`, y una compra `pendiente` con el bloqueo vencido, `vencida`. El proceso libera las sillas como máximo 2 minutos después (RNF-18).

**Validación.** Como en la iteración 1: tipo y formato los valida Pydantic (`422 datos_invalidos` con `campos`) y las reglas de negocio el `service.py`, con los códigos de cada tabla. Las reglas que cruzan campos (una clase por tramo, documento repetido) van en el service, para que el error quede en el campo exacto. Los topes de viajeros de los schemas (20) son técnicos: el máximo de negocio de 5 tiquetes por vuelo lo valida el service con `limite_tiquetes`, porque debe poder configurarse (RNF-23).

### Errores comunes

Además de los de [`README.md`](README.md) y de la [iteración 1](iteracion-1.md#errores-comunes):

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 403 | `correo_no_verificado` | Reservar, iniciar o confirmar una compra, o pagar una reserva, sin el correo verificado (HU-02). Mensaje: «Verifica tu correo para reservar o comprar.» |
| 404 | `no_encontrado` | La selección, reserva, compra o tarjeta no existe o es de otro cliente. |
| 409 | `vuelo_no_disponible` | Un vuelo del cuerpo no existe, está cancelado o ya se realizó. Mensaje: «Uno de los vuelos ya no está a la venta.»; `campos["tramos.N.vuelo_id"]`: «El vuelo no existe o ya no está programado.» |
| 409 | `fuera_de_plazo` | El vuelo está programado pero ya pasó su límite de venta (SUP-07). Mensaje: «La venta de STA-00076 ya cerró: cierra 1 hora antes de la salida (3 horas si es internacional).»; `campos["tramos.N.vuelo_id"]`: «Ya no se puede reservar ni comprar.» |
| 422 | `regreso_invalido` | El regreso no sale del destino de la ida, sale antes de su llegada o es el mismo vuelo (RF-28). Mensaje: «El regreso debe salir de Nueva York después de la llegada de la ida.»; `campos["tramos.1.vuelo_id"]`: «Elige un regreso que salga después de tu llegada.» |
| 409 | `clase_agotada` | No quedan sillas suficientes en la clase de algún tramo (RF-33, SUP-12). Sin `campos`. Mensaje: «No quedan sillas suficientes en esta clase.» (`reservas.sillas.SillasInsuficientes`) |
| 409 | `limite_tiquetes` | El cliente pasaría de 5 tiquetes activos en algún vuelo, sumando reservados, comprados y bloqueados (RF-32, SUP-09). Sin `campos`. Mensaje: «Un cliente puede tener máximo 5 tiquetes activos en el mismo vuelo.» (`reservas.service.LimiteDeTiquetes`) |
| 409 | `viajero_duplicado` | Un documento ya tiene un tiquete activo en el vuelo, de este o de otro cliente, o está repetido en la solicitud (RF-34, SUP-10). Nunca dice quién tiene el otro tiquete. Mensaje: «Uno de los documentos ya tiene un tiquete activo en este vuelo.»; `campos["viajeros.N.numero_documento"]`: «Este documento ya tiene un tiquete activo en este vuelo.», también para un documento repetido en la lista (`reservas.service.ViajeroDuplicado`). |
| 422 | `menor_sin_adulto` | En algún tramo ningún viajero tiene 18 años el día de la salida (RF-35, SUP-11). Mensaje: «Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.»; `campos["viajeros.N.fecha_nacimiento"]` en cada menor, con el mismo texto (`reservas.service.MenorSinAdulto`). |
| 409 | `saldo_insuficiente` | El saldo no alcanza (RF-39). No se cobra nada y las sillas siguen bloqueadas o reservadas. Mensaje: «Tu saldo no alcanza: te faltan $ 300.000.» |
| 409 | `bloqueo_vencido` | Confirmar una compra cuyo bloqueo de 15 minutos venció o se soltó (SUP-15). Mensaje: «Las sillas se liberaron porque pasaron 15 minutos sin confirmar. Vuelve a empezar la compra.» |
| 409 | `reserva_no_vigente` | Pagar una reserva vencida, cancelada o ya pagada (HU-27). Mensaje: «La reserva ya no está vigente: venció, se canceló o ya está pagada.» |
| 409 | `estado_invalido` | Confirmar o soltar una compra que ya está pagada. Mensaje: «La compra ya está pagada.» |
| 422 | `rango_invalido` | Un rango con el mínimo mayor que el máximo o la fecha final antes de la inicial, o un regreso con fecha anterior a la ida. Mensaje: «Revisa los rangos marcados.»; `campos` con el extremo que falla. |
| 422 | `tarjeta_invalida` | El número no pasa el algoritmo de Luhn (RF-46). Mensaje: «Revisa los datos de la tarjeta.»; `campos.numero`: «El número no es válido. Revisa los dígitos.» |
| 422 | `tarjeta_vencida` | La tarjeta ya venció: al registrarla (`campos.vencimiento`: «La tarjeta está vencida.») o al recargar con ella (`campos.tarjeta_id`: «La tarjeta está vencida. Elige otra o registra una nueva.»). |
| 501 | `no_implementado` | El endpoint todavía es un stub. |

Los montos de los mensajes van en COP con punto de miles («$ 300.000»), igual que en la interfaz (IU-06).

## Endpoints por historia

### Módulo busqueda · dueño: Backend A

#### Tipos del módulo

`VueloBusqueda`, cada resultado de la búsqueda y de los regresos:

```json
{
  "id": 131,
  "codigo": "STA-00131",
  "tipo": "nacional",
  "origen": { "codigo": "PEI", "nombre": "Pereira", "zona_horaria": "America/Bogota" },
  "destino": { "codigo": "BOG", "nombre": "Bogotá", "zona_horaria": "America/Bogota" },
  "salida": "2027-04-15T11:00:00Z",
  "llegada": "2027-04-15T11:45:00Z",
  "duracion_minutos": 45,
  "economica": {
    "precio_base": 262500,
    "precio_vigente": 210000,
    "promocion": { "porcentaje": 20, "fin": "2027-04-10T04:59:00Z" },
    "disponibles": 12,
    "agotada": false
  },
  "primera": {
    "precio_base": 690000,
    "precio_vigente": 690000,
    "promocion": null,
    "disponibles": 4,
    "agotada": false
  },
  "agotado": false
}
```

- `precio_vigente` es el precio con la promoción vigente de esa clase (RF-24); `promocion` es `null` si no hay.
- `disponibles` descuenta las sillas vendidas, las reservadas y las bloqueadas por compras pendientes. `agotada` es `disponibles = 0`; `agotado` es `true` si ninguna de las dos clases tiene sillas (SUP-20).
- `PaginaVuelosBusqueda`: `{ "items": [VueloBusqueda], "total": 24, "pagina": 1, "por_pagina": 20 }`.

#### HU-20 Buscar vuelos

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/busqueda/vuelos` | Público | `200 PaginaVuelosBusqueda` |
| GET | `/api/v1/ciudades` | Público | `200 Ciudad[]` (iteración 1, para los selectores de origen y destino) |

Parámetros, todos opcionales. Los filtros se combinan: un vuelo aparece solo si cumple todos (RF-27).

| Parámetro | Tipo | Filtro |
|---|---|---|
| `codigo` | texto, hasta 20 | Parte del código, sin distinguir mayúsculas: `STA-0003` encuentra STA-00030 a STA-00039. |
| `origen`, `destino` | código de ciudad (`PEI`) | Ciudad de salida o de llegada. Un código que no está en el catálogo no es un error: no hay vuelos que lo cumplan. |
| `tipo` | `nacional` \| `internacional` | |
| `fecha_desde`, `fecha_hasta` | `aaaa-mm-dd` | Día de la salida en la hora local del origen, ambos extremos incluidos. |
| `hora_desde`, `hora_hasta` | `hh:mm` | Hora de la salida en la hora local del origen, ambos extremos incluidos. Las franjas del wireframe las traduce el frontend: madrugada 00:00–05:59, mañana 06:00–11:59, tarde 12:00–17:59, noche 18:00–23:59. |
| `duracion_min`, `duracion_max` | minutos | Duración del vuelo, ambos extremos incluidos. |
| `precio_min`, `precio_max` | COP | Sobre el precio vigente de `clase`; sin `clase`, sobre el menor precio vigente de las dos. |
| `clase` | `economica` \| `primera` | Elige el precio que se filtra y se ordena. No quita los vuelos agotados en esa clase: salen marcados (SUP-20). |
| `orden` | `precio` (por defecto), `fecha`, `duracion` | Siempre ascendente; empates por salida y luego por id. `precio` usa el mismo precio del filtro. |
| `pagina`, `por_pagina` | entero | 20 por página por defecto (SUP-20), máximo 100. |

Ejemplo: «Vuelos desde Pereira con precio entre $ 200.000 y $ 400.000 en económica» es `GET /api/v1/busqueda/vuelos?origen=PEI&precio_min=200000&precio_max=400000&clase=economica`.

Reglas:

- Solo aparecen vuelos `programado` que no han llegado a su límite de venta: los realizados, los cancelados, los que ya salieron y los que ya no se pueden reservar ni comprar no aparecen (HU-20).
- `total` alimenta el título «24 vuelos desde Pereira».
- Con sesión de **cliente**, la primera página de cada búsqueda se registra para la recomendación (RF-29, RF-60): los criterios (los parámetros enviados y `orden`), la fecha y hora y la cantidad de resultados (`total`). No se registran las páginas siguientes de la misma búsqueda ni las búsquedas de visitantes, administradores o root.
- RNF-01: con 100 usuarios concurrentes, p95 ≤ 2 s. El precio y la ocupación de una página salen en un número fijo de consultas, no en una por vuelo.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 422 | `rango_invalido` | `precio_min` > `precio_max` (`campos.precio_max`: «Debe ser mayor o igual que el precio mínimo.»), `fecha_hasta` < `fecha_desde` (`campos.fecha_hasta`: «La fecha final no puede ser anterior a la inicial.»), `hora_hasta` < `hora_desde` (`campos.hora_hasta`: «La hora final no puede ser anterior a la inicial.») o `duracion_max` < `duracion_min` (`campos.duracion_max`: «Debe ser mayor o igual que la duración mínima.»). Si fallan varios, vienen todos. |
| 422 | `datos_invalidos` | Formato: código de ciudad que no son tres mayúsculas, fecha u hora inválidas, números negativos, `orden` o `clase` desconocidos. |

#### HU-21 Buscar ida y regreso

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/busqueda/vuelos` | Público | `200 PaginaVuelosBusqueda` (paso 1: la ida) |
| GET | `/api/v1/busqueda/regresos` | Público | `200 PaginaVuelosBusqueda` (paso 2: el regreso) |

Paso 1, la ida: `GET /api/v1/busqueda/vuelos?origen=PEI&destino=JFK&fecha_desde=2027-04-15&fecha_hasta=2027-04-15`.

Paso 2, el regreso: `GET /api/v1/busqueda/regresos?vuelo_ida_id=101&destino=CTG&fecha=2027-04-22`.

| Parámetro | Tipo | |
|---|---|---|
| `vuelo_ida_id` | entero, obligatorio | El vuelo de ida elegido. |
| `destino` | código de ciudad, obligatorio | Ciudad de regreso; puede ser distinta del origen de la ida (Pereira → Nueva York → Cartagena). |
| `fecha` | `aaaa-mm-dd`, obligatorio | Día de salida del regreso, en la hora local de su origen (el destino de la ida). |
| `clase`, `orden`, `pagina`, `por_pagina` | | Igual que en HU-20. |

Reglas:

- Devuelve los vuelos a la venta que salen del destino de la ida hacia `destino`, el día `fecha`, y **estrictamente después de la llegada** de la ida (RF-28). Si la ida llega el 10/12 a las 16:30, ningún regreso que salga antes aparece. Los que salen antes no se devuelven; si el frontend quiere dibujarlos deshabilitados como el wireframe S15, lo decide con los datos de la ida.
- Sin regresos para esa fecha, la respuesta es una página vacía: el frontend lo informa y deja cambiar la fecha o la ciudad sin perder la ida.
- El precio del trayecto es la suma de los precios vigentes de ambos vuelos, sin descuento combinado (RF-40): lo suma el frontend y el carrito lo confirma en `subtotal`.
- Con sesión de cliente, la primera página se registra igual que en HU-20, con `vuelo_ida_id`, `destino` y `fecha` como criterios.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | La ida no existe o ya no está a la venta. Mensaje: «El vuelo de ida no existe o ya no está a la venta.» |
| 422 | `rango_invalido` | `fecha` es anterior a la fecha de salida de la ida (hora local de su origen). `campos.fecha`: «La fecha de regreso no puede ser anterior a la de ida.» |
| 422 | `datos_invalidos` | Falta un parámetro obligatorio o tiene formato inválido. |

### Módulo carrito · dueño: Backend A

#### Tipos del módulo

`Carrito`, que devuelve `GET /carrito`:

```json
{
  "selecciones": [
    {
      "id": 71,
      "tramos": [
        {
          "vuelo": {
            "id": 131,
            "codigo": "STA-00131",
            "tipo": "nacional",
            "origen": { "codigo": "PEI", "nombre": "Pereira", "zona_horaria": "America/Bogota" },
            "destino": { "codigo": "BOG", "nombre": "Bogotá", "zona_horaria": "America/Bogota" },
            "salida": "2027-04-15T11:00:00Z",
            "llegada": "2027-04-15T11:45:00Z",
            "duracion_minutos": 45,
            "estado": "programado"
          },
          "clase": "economica",
          "precio_unitario": 210000,
          "precio_al_agregar": 262500,
          "promocion_porcentaje": 20,
          "disponibles": 12,
          "tiquetes_activos": 3
        }
      ],
      "viajeros": 2,
      "subtotal": 420000,
      "confirmable": true,
      "avisos": [
        {
          "codigo": "precio_cambio",
          "mensaje": "El precio cambió de $ 262.500 a $ 210.000. Pagarás el precio nuevo.",
          "tramo": 0
        }
      ],
      "reserva_venceria_en": "2026-11-17T15:20:00Z",
      "agregada_en": "2026-11-05T14:00:00Z"
    }
  ],
  "cantidad": 1,
  "total": 420000
}
```

- Cada lectura recalcula todo: `precio_unitario` es el precio vigente hoy por viajero y `precio_al_agregar` el de cuando se agregó o se modificó la selección. `tiquetes_activos` son los tiquetes activos del cliente en ese vuelo (para «Llevas 3 en STA-00131»).
- `subtotal` = suma de `precio_unitario × viajeros` de los tramos (RF-40). `total` suma solo las selecciones confirmables y `cantidad` es el número de selecciones (el contador «Carrito (2)» del menú).
- `reserva_venceria_en`: si se reservara ahora, `min(ahora + 24 h, límite de venta del tramo más próximo)` (SUP-07); `null` si no es confirmable. Es lo que S17 muestra en «Congela el precio y las sillas hasta…».
- Las selecciones van de la más reciente a la más antigua.

`avisos` (uno por cada problema y tramo; `confirmable` es `false` si hay cualquier aviso distinto de `precio_cambio`):

| `codigo` | ¿Confirmable? | `mensaje` |
|---|---|---|
| `precio_cambio` | Sí | «El precio cambió de $ 262.500 a $ 210.000. Pagarás el precio nuevo.» |
| `clase_agotada` | No | «Ya no quedan sillas suficientes en económica. Cambia de clase o quita este vuelo.» |
| `limite_tiquetes` | No | «Ya tienes 4 tiquetes activos en STA-00135 y el máximo por vuelo es 5.» |
| `vuelo_no_disponible` | No | «STA-00044 ya no está a la venta: se canceló o ya se realizó.» |
| `fuera_de_plazo` | No | «La venta de STA-00076 ya cerró.» |

#### HU-22 Agregar vuelos al carrito

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/carrito/selecciones` | Cliente | `201 SeleccionCarrito` |

`SeleccionEntrada`, un trayecto único (un tramo) o completo (dos):

```json
{
  "tramos": [
    { "vuelo_id": 101, "clase": "primera" },
    { "vuelo_id": 132, "clase": "economica" }
  ],
  "viajeros": 2
}
```

Reglas:

- El carrito se guarda en la base de datos, por cliente: sigue ahí después de cerrar sesión (SUP-15). Admite selecciones de rutas distintas y no tiene tope de selecciones. No exige el correo verificado: eso se pide al reservar o comprar.
- En el carrito **no se bloquean sillas**: se bloquean al iniciar la compra (HU-25).
- Al agregar se valida, en este orden: cada vuelo existe y está programado (`vuelo_no_disponible`) y sigue a la venta (`fuera_de_plazo`); con dos tramos, el regreso (`regreso_invalido`); el límite de 5 (`limite_tiquetes`: tiquetes activos del cliente en el vuelo + `viajeros` > 5); el cupo de la clase (`clase_agotada`).
- El límite no suma otras selecciones del carrito: se vuelve a validar al reservar o comprar.
- `precio_al_agregar` queda con el precio vigente del momento.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 409 | `vuelo_no_disponible`, `fuera_de_plazo` | Ver errores comunes. |
| 422 | `regreso_invalido` | Ver errores comunes. |
| 409 | `limite_tiquetes` | Un cliente con 3 tiquetes comprados y 2 reservados en un vuelo intenta agregar otro de ese vuelo. |
| 409 | `clase_agotada` | La clase elegida no tiene sillas para todos los viajeros. |
| 422 | `datos_invalidos` | `tramos` vacío o con más de dos, `viajeros` menor que 1, clase desconocida. |

#### HU-23 Revisar y modificar el carrito

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/carrito` | Cliente | `200 Carrito` |
| PATCH | `/api/v1/carrito/selecciones/{seleccion_id}` | Cliente | `200 SeleccionCarrito` |
| DELETE | `/api/v1/carrito/selecciones/{seleccion_id}` | Cliente | `204` |
| DELETE | `/api/v1/carrito` | Cliente | `204` |

`SeleccionCambio`, con solo lo que cambia:

```json
{ "viajeros": 3, "clases": ["economica"] }
```

- `clases` trae una clase por tramo, en el orden de la selección. Con un número distinto de tramos responde `422 datos_invalidos` con `campos.clases`: «Debe traer una clase por cada tramo.»
- Modificar vuelve a validar el límite y el cupo con los valores nuevos (`limite_tiquetes`, `clase_agotada`) y deja `precio_al_agregar` en el precio vigente: el cliente ya vio el cambio. Un cuerpo vacío no cambia nada.
- Quitar una selección o vaciar el carrito es inmediato. Vaciar un carrito vacío también responde `204`.
- Desde el carrito se confirma cada selección por separado: el frontend pasa a `/compra/viajeros?seleccion=<id>` (ver [Rutas del frontend](#rutas-del-frontend)).
- Después de reservar (`201`) o de confirmar la compra (`200`), el frontend quita la selección con `DELETE /carrito/selecciones/{seleccion_id}`. El backend de reservas no toca el carrito.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | La selección no existe o es de otro cliente. Mensaje: «La selección no existe.» |
| 409 | `limite_tiquetes`, `clase_agotada` | Al modificar, como al agregar. |
| 422 | `datos_invalidos` | `campos.clases` o `campos.viajeros`. |

### Módulo reservas · dueño: Backend B

#### Tipos del módulo

`ViajeEntrada`, el mismo cuerpo para reservar y para iniciar una compra:

```json
{
  "tramos": [{ "vuelo_id": 131 }],
  "viajeros": [
    {
      "tipo_documento": "CC",
      "numero_documento": "1088345921",
      "nombres": "Laura",
      "apellidos": "Gómez Ríos",
      "fecha_nacimiento": "1995-03-14",
      "genero": "femenino",
      "telefono": "310 555 0192",
      "email": "laura.gomez@correo.co",
      "contacto_nombre": "Jorge Gómez",
      "contacto_telefono": "311 555 0101",
      "clases": ["economica"]
    }
  ]
}
```

- `tramos`: uno o dos (ida y regreso). `viajeros`: al menos uno (tope técnico de 20; el de negocio lo da `limite_tiquetes`).
- Datos del viajero (RF-31), con las mismas reglas de formato de HU-01: `tipo_documento` (`CC`, `TI`, `RC`, `CE` o `PA`), `numero_documento` (alfanumérico, 3 a 20, sin espacios ni puntos), `nombres` y `apellidos` (1 a 100, empiezan por letra), `fecha_nacimiento`, `genero` (`femenino`, `masculino` u `otro`), `telefono`, `email`, `contacto_nombre` (1 a 100) y `contacto_telefono` son obligatorios: un campo vacío o un correo con formato inválido se rechaza en el viajero que corresponde (RF-31). Así cada viajero recibe el código de reserva (HU-25). Si el cliente viaja, el frontend autocompleta sus datos con `GET /usuarios/me/perfil` («Soy yo»).
- `clases`: una por tramo, en el orden de `tramos`. En un trayecto completo cada viajero puede ir en una clase distinta en cada tramo.

`Viaje`, la forma de una reserva y de una compra:

```json
{
  "id": 41,
  "tipo": "reserva",
  "codigo": "H4N8WQ",
  "estado": "vigente",
  "reserva_id": null,
  "compra_id": null,
  "creada_en": "2026-11-16T15:20:00Z",
  "vence_en": "2026-11-17T15:20:00Z",
  "pagada_en": null,
  "total": 787500,
  "total_pendiente": 787500,
  "tramos": [
    {
      "vuelo": {
        "id": 131,
        "codigo": "STA-00131",
        "tipo": "nacional",
        "origen": { "codigo": "PEI", "nombre": "Pereira", "zona_horaria": "America/Bogota" },
        "destino": { "codigo": "BOG", "nombre": "Bogotá", "zona_horaria": "America/Bogota" },
        "salida": "2027-04-15T11:00:00Z",
        "llegada": "2027-04-15T11:45:00Z",
        "duracion_minutos": 45,
        "estado": "programado"
      }
    }
  ],
  "viajeros": [
    {
      "id": 4101,
      "tipo_documento": "CC",
      "numero_documento": "1088345921",
      "nombres": "Laura",
      "apellidos": "Gómez Ríos",
      "fecha_nacimiento": "1995-03-14",
      "genero": "femenino",
      "telefono": "310 555 0192",
      "email": "laura.gomez@correo.co",
      "contacto_nombre": "Jorge Gómez",
      "contacto_telefono": "311 555 0101",
      "tiquetes": [
        {
          "id": 41010,
          "tramo": 0,
          "clase": "economica",
          "silla": "18C",
          "numero_silla": 88,
          "precio": 262500,
          "estado": "reservado"
        }
      ]
    }
  ]
}
```

| Campo | Significado |
|---|---|
| `tipo` | `reserva` o `compra`. |
| `codigo` | Código de reserva: 6 caracteres de `A`–`Z` y `2`–`9`, sin `O`, `I`, `0` ni `1` para no confundirlos. Una reserva lo tiene desde que se crea; una compra directa, desde que se inicia (solo se envía por correo al confirmarla). Al pagar una reserva, su compra conserva el mismo código. Nunca es `null`. |
| `estado` | Reserva: `vigente`, `pagada` (todos sus viajeros pagados), `vencida` o `cancelada` (la iteración 3 agrega la cancelación por el cliente; hoy solo la cancelación del vuelo, HU-16). Compra: `pendiente` (sillas bloqueadas, sin pagar), `vencida` (el bloqueo de 15 minutos pasó sin confirmar), `cancelada` (el cliente soltó el bloqueo con `DELETE /compras/{id}`, o se canceló el vuelo antes de pagar) o `activa` (pagada). La iteración 3 usa los demás estados del modelo de #138 (`realizada`, `reembolsada`, `reubicada`) y la cancelación de una compra pagada, de RF-45. |
| `reserva_id` | En una compra que viene de pagar una reserva, esa reserva. |
| `compra_id` | En una reserva pagada (toda o en parte), la compra con sus viajeros pagados. |
| `vence_en` | Reserva: su vencimiento (también en las vencidas: «Vencida el 01/10/2026 09:02»). Compra `pendiente`, `vencida` o soltada sin pagar (`cancelada`): fin del bloqueo de 15 minutos (la cuenta regresiva de S18; en el modelo es `bloqueo_hasta`). Compra pagada (`activa`): `null`. |
| `pagada_en` | Último pago de una compra; `null` en reservas y en compras sin pagar. |
| `total` | Suma de los precios congelados de todos los tiquetes. |
| `total_pendiente` | Lo que falta pagar: tiquetes `reservado` o `bloqueado`. Es lo que cobra pagar la reserva completa o confirmar la compra. |
| `tiquetes[].estado` | `bloqueado` (compra pendiente), `reservado`, `comprado`, `cancelado` (se soltó el bloqueo, se canceló el vuelo o, en la iteración 3, el cliente cancela), `vencido` (venció la reserva o el bloqueo), y los de la iteración 3 `reembolsado` y `reubicado`. En una reserva, el tiquete de un viajero que ya se pagó queda `comprado` (vive en la compra con el mismo código). |
| `tiquetes[].silla` | Fila y letra (`18C`, SUP-26) con `vuelos.service.nombre_de_silla`; `numero_silla` es el número interno. |

`PaginaViajes`: `{ "items": [Viaje], "total": 3, "pagina": 1, "por_pagina": 20 }`.

#### Reglas comunes de reservar y comprar

`POST /reservas` y `POST /compras` validan, **en este orden**, y responden el primer error:

1. `403 correo_no_verificado` (HU-02). El dato sale de `usuarios.service.obtener_perfil`.
2. Por tramo: `409 vuelo_no_disponible` y `409 fuera_de_plazo`.
3. Con dos tramos: `422 regreso_invalido`.
4. Por viajero: `422 datos_invalidos` si `clases` no trae una clase por tramo (`campos["viajeros.N.clases"]`: «Debe traer una clase por cada tramo.») o con `reservas.service.validar_viajeros`: campo obligatorio vacío, correo con formato inválido, género desconocido o fecha de nacimiento futura o de hace más de 120 años (RF-31, SUP-43; el error de la fecha sale de `usuarios.service.validar_fecha_nacimiento`, reubicado en `viajeros.N.fecha_nacimiento`).
5. `409 viajero_duplicado` (`validar_documentos_en_vuelo`, una llamada por vuelo): un documento repetido en la solicitud o con un tiquete activo (reservado, comprado o bloqueado) en alguno de los vuelos. El documento es tipo + número, sin distinguir mayúsculas.
6. `422 menor_sin_adulto` (`validar_menores`, una llamada por vuelo): en algún tramo ningún viajero tiene 18 años o más el día de la salida (fecha local del origen). Quien cumple 18 ese día o antes ya es adulto y puede viajar solo.
7. `409 limite_tiquetes` (`validar_limite_de_tiquetes`): por cada vuelo, tiquetes activos del cliente + viajeros > 5 (RF-32).
8. `409 clase_agotada` (`validar_cupo`, una llamada por vuelo y clase): viajeros que la piden > sillas disponibles (RF-33).

Si todo pasa, en una sola transacción (RNF-17): se asignan las sillas con `reservas.sillas.asignar_sillas`, una llamada por vuelo y clase (2 en primera y 3 en económica reciben un bloque en cada clase, RF-41); el precio de cada tiquete se congela con `vuelos.service.precio_vigente`; se genera el código. Si un tramo incumple una regla, no se crea nada (HU-26).

Concurrencia (RF-42): las asignaciones sobre un mismo vuelo se serializan y los índices únicos parciales de `tiquetes` (#138) impiden dos tiquetes activos en la misma silla o con el mismo documento. Si otra transacción tomó las sillas elegidas, se eligen otras en la misma petición; si ya no hay, `clase_agotada`. Con dos vuelos, se toman en orden de id para no bloquearse entre sí.

#### HU-24 Reservar tiquetes

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/reservas` | Cliente verificado | `201 Viaje` (`tipo: "reserva"`, `estado: "vigente"`) |
| GET | `/api/v1/usuarios/me/perfil` | Cliente | `200 PerfilSalida` (iteración 1, para «Soy yo») |

- Cuerpo `ViajeEntrada` y las [reglas comunes](#reglas-comunes-de-reservar-y-comprar).
- La reserva no cobra nada: bloquea las sillas asignadas y congela el precio (RF-36).
- `vence_en = min(creada_en + 24 h, límite de venta del tramo más próximo)`. Una reserva hecha 10 horas antes de un vuelo nacional vence 1 hora antes de la salida; una hecha 3 días antes vence a las 24 horas.
- Mientras esté vigente, sus sillas no están disponibles para nadie más y el vuelo no se puede editar (HU-15).
- Proceso automático `reservas.vencer_reservas`, cada minuto: toda reserva vigente con `vence_en` pasado queda `vencida`, sus tiquetes `vencido`, sus sillas libres y se encola un correo al cliente («Tu reserva H4N8WQ venció»). Como máximo 2 minutos de atraso y al arrancar el servidor (RF-37, RNF-18). Correrla dos veces no cambia nada la segunda vez.
- Crear la reserva no envía correo: el código se ve en la respuesta y en Mis viajes, y viaja por correo al pagarla.
- Al cancelar un vuelo (HU-16), `anular_reservas_de_vuelo` deja sus reservas vigentes `cancelada`, libera las sillas (sus tiquetes quedan `cancelado`), cancela las compras pendientes del vuelo (`cancelada`) y encola el correo a cada cliente.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 403 | `correo_no_verificado` | Cliente sin el correo verificado. |
| 409 | `vuelo_no_disponible`, `fuera_de_plazo` | El vuelo no se vende o ya pasó su límite (SUP-07). |
| 409 | `viajero_duplicado` | `campos["viajeros.N.numero_documento"]`. |
| 409 | `limite_tiquetes`, `clase_agotada` | Ver errores comunes. |
| 422 | `menor_sin_adulto` | Un único viajero de 16 años. |
| 422 | `datos_invalidos` | Campo obligatorio vacío, correo con formato inválido, `viajeros.N.clases`, `viajeros.N.fecha_nacimiento` (RF-31). |

#### HU-25 Comprar tiquetes

La compra va en dos pasos, como los wireframes S17 y S18: iniciar (asigna y bloquea las sillas) y confirmar (cobra).

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/compras` | Cliente verificado | `201 Viaje` (`tipo: "compra"`, `estado: "pendiente"`) |
| GET | `/api/v1/compras/{compra_id}` | Cliente | `200 Viaje` |
| POST | `/api/v1/compras/{compra_id}/confirmar` | Cliente verificado | `200 Viaje` (`estado: "activa"`) |
| DELETE | `/api/v1/compras/{compra_id}` | Cliente | `204` |
| GET | `/api/v1/monedero` | Cliente | `200 Monedero` (HU-31: saldo actual y «saldo después») |

Iniciar (`POST /compras`):

- Cuerpo `ViajeEntrada` y las [reglas comunes](#reglas-comunes-de-reservar-y-comprar). Asigna las sillas, congela el precio y genera el código.
- Las sillas quedan bloqueadas hasta `vence_en = min(creada_en + 15 min, límite de venta del tramo más próximo)` (SUP-15). Mientras tanto cuentan como ocupadas, para el límite de 5 y para el documento duplicado.
- Proceso automático `reservas.liberar_bloqueos`, cada minuto: toda compra pendiente con el bloqueo vencido queda `vencida`, sus tiquetes `vencido` y sus sillas libres (RNF-18).

Consultar (`GET /compras/{compra_id}`): cualquier compra del cliente, en el estado efectivo (una pendiente con el bloqueo vencido se devuelve `vencida`).

Confirmar (`POST /compras/{compra_id}/confirmar`, sin cuerpo), en una sola transacción (RNF-17):

1. Valida en este orden: `404`, `403 correo_no_verificado`, `409 estado_invalido` (ya está `activa`), `409 bloqueo_vencido` (`vencida`, `cancelada` o `vence_en` pasado), `409 saldo_insuficiente`.
2. Cobra `total_pendiente` con `monedero.service.debitar(..., referencia=codigo)`. Con saldo insuficiente no cobra nada y las sillas siguen bloqueadas hasta que venza el bloqueo, para recargar y volver (S18).
3. Los tiquetes pasan a `comprado`, la compra a `activa` y `pagada_en` toma la hora.
4. Encola un correo con el código, el vuelo y su silla a cada viajero, y otro al comprador (correo de su cuenta) con el comprobante en PDF de `reservas.comprobante.generar_comprobante` adjunto como `comprobante-<codigo>.pdf` (RF-39).
5. Si se vendió la última silla de una clase, llama a `vuelos.service.marcar_promociones_agotadas` (RF-23).

Si falla cualquier paso, no queda nada: ni movimiento, ni tiquetes comprados, ni correos.

Soltar (`DELETE /compras/{compra_id}`): una compra `pendiente` pasa a `cancelada` (sus tiquetes, a `cancelado`) y libera sus sillas; una ya `cancelada` o `vencida` responde `204` igual. El frontend vuelve al carrito.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 403 | `correo_no_verificado` | Al iniciar o confirmar. |
| 404 | `no_encontrado` | La compra no existe o es de otro cliente. Mensaje: «La compra no existe.» |
| 409 | `saldo_insuficiente` | Con $ 500.000 de saldo, una compra de $ 800.000. El mensaje dice cuánto falta; el frontend lo calcula también con `total_pendiente − saldo`. |
| 409 | `bloqueo_vencido` | Pasaron los 15 minutos o la compra se soltó. |
| 409 | `estado_invalido` | Confirmar o soltar una compra ya pagada. |
| 409 / 422 | | Al iniciar, los de las reglas comunes. |

#### HU-26 Reservar o comprar un trayecto completo

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/reservas` | Cliente verificado | `201 Viaje` con dos tramos |
| POST | `/api/v1/compras` | Cliente verificado | `201 Viaje` con dos tramos |
| GET | `/api/v1/busqueda/regresos` | Público | HU-21 |

```json
{
  "tramos": [{ "vuelo_id": 101 }, { "vuelo_id": 132 }],
  "viajeros": [
    {
      "tipo_documento": "CC",
      "numero_documento": "1088999000",
      "nombres": "Daniel",
      "apellidos": "Arango",
      "fecha_nacimiento": "1990-08-15",
      "genero": "masculino",
      "telefono": "311 555 0188",
      "email": "daniel.arango@correo.co",
      "contacto_nombre": "Laura Gómez",
      "contacto_telefono": "310 555 0192",
      "clases": ["primera", "economica"]
    }
  ]
}
```

- Un trayecto completo es **una** reserva o compra con un solo código y dos tiquetes por viajero, uno por tramo, cada uno con su silla (SUP-14).
- El regreso sale del destino de la ida, después de su llegada, y es otro vuelo; si no, `regreso_invalido` (RF-28). La ciudad de llegada del regreso puede ser distinta del origen de la ida.
- La clase se elige por viajero en cada tramo (`clases`). El total es la suma de los precios vigentes de ambos tramos, sin descuento combinado (RF-40): Pereira → Nueva York en primera ($ 4.100.000) y Nueva York → Cartagena en económica ($ 1.750.000) suman $ 5.850.000 por viajero.
- Las reglas comunes se validan en cada tramo; si uno falla, no se crea ninguno de los dos.
- La reserva vence en `min(creada_en + 24 h, límite de venta del tramo más próximo)` y el bloqueo de la compra en `min(creada_en + 15 min, ese mismo límite)`. En la práctica es el de la ida, salvo que el regreso salga muy pronto y sea internacional.
- El comprobante y los correos muestran los dos tramos. La cancelación de un trayecto completo llega en la iteración 3.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 422 | `regreso_invalido` | `campos["tramos.1.vuelo_id"]`. |
| 409 / 422 | | Los de las reglas comunes, en cualquiera de los dos tramos. |

#### HU-27 Pagar una reserva

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/mis-viajes` | Cliente | `200 PaginaViajes` |
| POST | `/api/v1/reservas/{reserva_id}/pagar` | Cliente verificado | `200 PagoReservaSalida` |
| GET | `/api/v1/monedero` | Cliente | `200 Monedero` |

`GET /mis-viajes` (las dos pestañas de S19):

| Parámetro | Tipo | |
|---|---|---|
| `tipo` | `reserva` \| `compra`, obligatorio | La pestaña. Las compras que nunca se pagaron (`pendiente`, `vencida` y `cancelada` sin `pagada_en`) no se listan. |
| `estado` | estado de `Viaje` | Reserva: `vigente`, `pagada`, `vencida`, `cancelada`. Compra: `activa` (y los de la iteración 3). Un estado del otro tipo no trae nada. |
| `desde`, `hasta` | `aaaa-mm-dd` | Día de salida del primer tramo, en hora de Colombia (el selector «Octubre de 2026» manda el primer y el último día del mes). |
| `pagina`, `por_pagina` | | 20 por defecto, máximo 100. |

Van de la más reciente a la más antigua (`creada_en`). Un cliente nunca ve las de otro. `hasta` anterior a `desde` responde `422 rango_invalido` con `campos.hasta`.

`PagoReservaEntrada`:

```json
{ "viajero_ids": [4101, 4102] }
```

Sin `viajero_ids` (o con `null`) se pagan todos los viajeros que siguen reservados.

`PagoReservaSalida`:

```json
{ "reserva": { "…": "Viaje", "estado": "vigente", "compra_id": 905, "total_pendiente": 262500 }, "compra": { "…": "Viaje", "id": 905, "tipo": "compra", "codigo": "H4N8WQ", "estado": "activa", "reserva_id": 41, "total": 525000 } }
```

Reglas:

- Se paga una reserva `vigente`, completa o por viajero, al **precio congelado** de la reserva aunque hoy el vuelo tenga una promoción (RF-38).
- Valida en este orden: `404`, `403 correo_no_verificado`, `409 reserva_no_vigente`, `422 datos_invalidos` (`campos.viajero_ids`: «Elige viajeros de esta reserva que sigan sin pagar.»), `422 menor_sin_adulto` y `409 saldo_insuficiente`.
- Un menor que se paga necesita un adulto en la compra de esa reserva, ya pagado o pagado en esta misma operación (RF-35): si no, `menor_sin_adulto` con `campos.viajero_ids`: «Paga también a un adulto: un menor no puede quedar solo en la compra.»
- Al pagar, los mismos efectos de la compra (HU-25) en una sola transacción: débito de lo pagado con el código como referencia, código por correo a los viajeros pagados y comprobante en PDF al comprador con lo pagado en esta operación.
- **El código no cambia.** La primera vez se crea la compra de la reserva con el mismo código (`reserva_id`); los pagos siguientes agregan sus tiquetes a esa misma compra. Las sillas son las mismas de la reserva. (Ver la nota sobre `transacciones.codigo` en «Funciones entre módulos › `reservas.service`».)
- Los viajeros que no se pagan siguen reservados con el **mismo vencimiento** (SUP-40): pagar 2 de 4 deja 2 tiquetes comprados y 2 reservados. Cuando no queda ninguno reservado, la reserva pasa a `pagada`.
- Si se vendió la última silla de una clase, llama a `vuelos.service.marcar_promociones_agotadas`.
- Con saldo insuficiente no cambia nada; el frontend ofrece recargar el valor faltante y volver (HU-30).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | La reserva no existe o es de otro cliente. Mensaje: «La reserva no existe.» |
| 409 | `reserva_no_vigente` | Reserva vencida, cancelada o ya pagada. |
| 409 | `saldo_insuficiente` | Ver errores comunes. |
| 422 | `datos_invalidos` | `campos.viajero_ids`. |
| 422 | `menor_sin_adulto` | `campos.viajero_ids`. |
| 422 | `rango_invalido` | `GET /mis-viajes` con `hasta` anterior a `desde`. |

### Módulo monedero · dueño: Backend A

#### Tipos del módulo

`Tarjeta`:

```json
{
  "id": 21,
  "tipo": "credito",
  "franquicia": "visa",
  "titular": "LAURA GOMEZ RIOS",
  "numero_enmascarado": "**** 4242",
  "vencimiento": "08/28",
  "vencida": false,
  "creada_en": "2026-09-29T15:05:00Z"
}
```

`Movimiento`:

```json
{
  "id": 37,
  "tipo": "compra",
  "valor": -900000,
  "saldo_resultante": 1000000,
  "referencia": "P3X7KD",
  "creado_en": "2026-11-03T16:20:00Z"
}
```

- `tipo`: `credito` o `debito`. `franquicia`: `visa`, `mastercard`, `amex`, `diners` u `otra`; la deduce el backend del número (Visa empieza por 4; Mastercard por 51–55 o 2221–2720; American Express por 34 o 37; Diners Club por 300–305, 36 o 38).
- `vencimiento`: `MM/AA`. Una tarjeta sirve hasta el último día de ese mes, en hora de Colombia; después `vencida` es `true`.
- `Movimiento.tipo`: `recarga`, `compra` o `reembolso` (la iteración 3 crea los reembolsos). `valor` lleva signo: positivo en recargas y reembolsos, negativo en compras. `referencia` es el código de reserva en compras y reembolsos, y `**** 1234` en recargas.
- `Monedero`: `{ "saldo": 1000000 }`. El saldo es la suma de todos los movimientos del cliente y nunca es negativo (RF-48).

#### HU-28 Registrar tarjeta

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/monedero/tarjetas` | Cliente | `201 Tarjeta` |

`TarjetaEntrada`:

```json
{
  "tipo": "credito",
  "titular": "LAURA GOMEZ RIOS",
  "numero": "4242424242424242",
  "vencimiento": "08/28",
  "cvv": "123"
}
```

- `numero`: 13 a 19 dígitos, sin espacios (el frontend los quita). Se valida con el algoritmo de Luhn (RF-46).
- `vencimiento`: `MM/AA`, no anterior al mes actual. `cvv`: 3 o 4 dígitos. `titular`: 1 a 100 caracteres, letras y espacios.
- Solo se guardan los últimos 4 dígitos y un token simulado. El número completo y el CVV se validan y se descartan: nunca llegan a la base de datos ni a los logs (RNF-12). La respuesta nunca los devuelve.
- Se puede registrar la misma tarjeta más de una vez.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 422 | `tarjeta_invalida` | `4242 4242 4242 4241` no pasa Luhn. `campos.numero`. |
| 422 | `tarjeta_vencida` | `campos.vencimiento`. |
| 422 | `datos_invalidos` | Formato de `numero`, `vencimiento`, `cvv` o `titular`. |

#### HU-29 Eliminar tarjeta

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/monedero/tarjetas` | Cliente | `200 Tarjeta[]` |
| DELETE | `/api/v1/monedero/tarjetas/{tarjeta_id}` | Cliente | `204` |

- El listado trae las tarjetas no eliminadas del cliente, de la más reciente a la más antigua, incluidas las vencidas (con `vencida: true`, para que pueda eliminarlas).
- Eliminar es un borrado lógico: la tarjeta deja de aparecer y de servir para recargar, y las recargas hechas con ella conservan su referencia (`**** 1234`). El frontend pide confirmación antes.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | La tarjeta no existe, es de otro cliente o ya se eliminó. Mensaje: «La tarjeta no existe.» |

#### HU-30 Recargar monedero

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| POST | `/api/v1/monedero/recargas` | Cliente | `201 Movimiento` |

```json
{ "tarjeta_id": 21, "valor": 500000 }
```

- `valor`: entero mayor que 0. No hay tope de negocio (SUP-21); el schema solo rechaza valores de un billón de pesos o más, para no desbordar la base de datos.
- La recarga se aprueba de forma simulada si la tarjeta es del cliente, no está eliminada y está vigente (RF-47). Registra un movimiento `recarga` con la referencia `**** 1234` y el saldo resultante: una recarga de $ 500.000 aumenta el saldo exactamente en $ 500.000.
- Si el cliente no tiene tarjetas, el frontend lo lleva a registrar una y vuelve a la recarga. Si llega desde una compra o una reserva con saldo insuficiente, propone el valor faltante y al terminar vuelve a donde estaba (ver [Rutas del frontend](#rutas-del-frontend)).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_encontrado` | La tarjeta no existe, es de otro cliente o se eliminó. |
| 422 | `tarjeta_vencida` | `campos.tarjeta_id`. |
| 422 | `datos_invalidos` | `campos.valor`: «Debe ser mayor que 0.» con un valor de 0 o negativo. |

#### HU-31 Consultar saldo y movimientos

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/v1/monedero` | Cliente | `200 Monedero` |
| GET | `/api/v1/monedero/movimientos` | Cliente | `200 PaginaMovimientos` |

Filtros de `GET /monedero/movimientos`: `tipo` (`recarga`, `compra` o `reembolso`), `desde` y `hasta` (`aaaa-mm-dd`, fecha del movimiento en hora de Colombia), `pagina` y `por_pagina` (20 por defecto, máximo 100). Van del más reciente al más antiguo.

- Un cliente sin movimientos tiene saldo 0 y una página vacía; el frontend ofrece recargar.
- El saldo es igual a la suma de los movimientos (RF-48, RNF-17) y cada movimiento trae el saldo resultante. Los movimientos no se editan ni se borran (RNF-16).

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 422 | `rango_invalido` | `hasta` anterior a `desde`. `campos.hasta`: «La fecha final no puede ser anterior a la inicial.» |

## Rutas del frontend

Cada pantalla ya tiene su ruta y una página vacía, para que ningún issue de pantalla edite `router.tsx`.

| Ruta | Pantalla | Rol | Issue | Parámetros |
|---|---|---|---|---|
| `/buscar` | S14 Resultados de búsqueda | Público | #121 | Libres: puede reflejar los filtros en la URL. |
| `/buscar/ida-y-regreso` | S15 Búsqueda de ida y regreso | Público | #122 | Libres. |
| `/carrito` | S16 Carrito | Cliente | #127 | — |
| `/compra/viajeros` | S17 Viajeros y reservar o comprar | Cliente | #128 | `?seleccion=<id>` (obligatorio). |
| `/compra/pago/:compraId` | S18 Pago con monedero | Cliente | #134 | `?seleccion=<id>` (opcional). |
| `/mis-viajes` | S19 Mis viajes | Cliente | #123 | `?tipo=reserva\|compra` (pestaña), `?pagar=<reserva_id>` (opcional: reabre el pago). |
| `/monedero` | S22 Monedero | Cliente | #132 | — |
| `/monedero/tarjetas/nueva` | S23 Registrar tarjeta | Cliente | #133 | `?volver=<ruta>` (opcional). |
| `/monedero/recargar` | S23 Recargar | Cliente | #133 | `?faltante=<COP>&codigo=<código>&volver=<ruta>` (opcionales). |

En el menú, «Vuelos» lleva a `/buscar` (visitante y cliente) y el cliente tiene además «Carrito», «Mis viajes» y «Monedero». A un visitante, agregar al carrito lo lleva a `/login?next=<ruta actual>`.

Flujos:

- **Carrito → viajeros.** «Continuar» en una selección confirmable abre `/compra/viajeros?seleccion=71`. La página lee la selección de `GET /carrito`; si un viajero cambia de clase, el precio y la disponibilidad de la otra salen de `GET /vuelos/{vuelo_id}` (HU-19).
- **Reservar.** `POST /reservas` → `201` → `DELETE /carrito/selecciones/71` → `/mis-viajes?tipo=reserva`.
- **Comprar.** `POST /compras` → `201` → `/compra/pago/<compra_id>?seleccion=71` → confirmar `200` → `DELETE /carrito/selecciones/71`. «Cancelar» hace `DELETE /compras/<compra_id>` y vuelve a `/carrito`.
- **Saldo insuficiente al comprar.** `/monedero/recargar?faltante=300000&codigo=K7Q2PX&volver=%2Fcompra%2Fpago%2F901%3Fseleccion%3D71`. Tras recargar, vuelve a `volver` y la compra sigue con sus sillas si el bloqueo no venció.
- **Saldo insuficiente al pagar una reserva.** `/monedero/recargar?faltante=…&codigo=H4N8WQ&volver=%2Fmis-viajes%3Ftipo%3Dreserva%26pagar%3D41`.
- **Sin tarjetas.** `/monedero/recargar` lleva a `/monedero/tarjetas/nueva?volver=<la URL de la recarga, codificada>`; tras registrar, vuelve con los mismos parámetros.
- `faltante` es `total_pendiente − saldo`. `volver` va codificado con `encodeURIComponent` y solo se acepta si es una ruta interna (empieza por `/` y no por `//` ni `/\`, la misma regla de `destinoTrasLogin`); si no, se vuelve a `/monedero`.

## Funciones entre módulos

Cuando un módulo necesita a otro, llama a estas funciones públicas del `service.py` del dueño. Ninguna hace commit: corren dentro de la transacción de quien llama (RNF-17). Los tipos de retorno son dataclasses del `service.py` del dueño, porque nadie importa `schemas.py` ni `models.py` ajenos. Cada dueño crea las suyas en su issue; este issue solo agrega `vuelos.service.limite_de_venta`, porque la usan cuatro issues a la vez, y no toca ningún otro `service.py`. Lo que ya existe en `main` está marcado como tal y se describe como es.

### `vuelos.service` · `limite_de_venta` ya existe (#112); `buscar_vuelos` y `regresos_de` los agrega #120 · lo llaman busqueda, carrito y reservas

```python
OrdenBusqueda = Literal["precio", "fecha", "duracion"]


@dataclass(frozen=True)
class FiltrosBusqueda:
    """Filtros de RF-27; None = sin filtro. Fechas y horas, locales del origen de cada vuelo."""

    codigo: str | None = None
    origen: str | None = None
    destino: str | None = None
    tipo: TipoVuelo | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    hora_desde: time | None = None
    hora_hasta: time | None = None
    duracion_min: int | None = None
    duracion_max: int | None = None
    precio_min: int | None = None
    precio_max: int | None = None
    clase: Clase | None = None


@dataclass(frozen=True)
class PaginaVuelosBuscados:
    """Página de resultados: cada item es el VueloDetalleGestion que ya usa el detalle (HU-19)."""

    items: list[VueloDetalleGestion]
    total: int
    pagina: int
    por_pagina: int


def limite_de_venta(tipo: TipoVuelo, salida: datetime) -> datetime:
    """Hasta cuándo se reserva o se compra un vuelo: 1 h antes de la salida si es nacional y 3 h
    si es internacional (SUP-07, RF-36). Es también el límite de cancelación de RF-43."""


def buscar_vuelos(
    db: Session,
    filtros: FiltrosBusqueda,
    *,
    orden: OrdenBusqueda = "precio",
    pagina: int = 1,
    por_pagina: int = 20,
    ahora: datetime | None = None,
) -> PaginaVuelosBuscados:
    """Vuelos programados antes de su límite de venta que cumplen todos los filtros (RF-27).

    Fechas y horas se comparan con la salida en la hora local del origen. El precio se filtra y
    se ordena sobre el precio vigente de `clase`, o sobre el menor de las dos sin `clase`. Orden
    ascendente con desempate por salida e id. Los vuelos sin cupo se incluyen. No valida que
    los rangos tengan sentido (eso lo hace busqueda). Precio y ocupación de la página en un
    número fijo de consultas, con reservas.ocupacion_de_vuelos (RNF-01). No hace commit.
    """


def regresos_de(
    db: Session,
    vuelo_ida_id: int,
    ciudad_regreso: str,
    fecha: date,
    *,
    clase: Clase | None = None,
    orden: OrdenBusqueda = "precio",
    pagina: int = 1,
    por_pagina: int = 20,
    ahora: datetime | None = None,
) -> PaginaVuelosBuscados:
    """Regresos de un trayecto completo (RF-28): vuelos a la venta desde el destino de la ida
    hacia `ciudad_regreso`, que salen el día `fecha` (hora local de su origen) y después de la
    llegada de la ida.

    Lanza NoEncontrado si la ida no existe o ya no está a la venta, y
    DatosInvalidos(codigo="rango_invalido", campos={"fecha": ...}) si `fecha` es anterior a la
    fecha de salida de la ida en la hora local de su origen. No hace commit.
    """
```

Las de la iteración 1 que se usan ahora:

| Función | Quién y para qué |
|---|---|
| `obtener_vuelo_detalle(db, vuelo_id, *, ahora=None) -> VueloDetalleGestion` | carrito y reservas: datos del vuelo, precio vigente y disponibilidad por clase. `NoEncontrado` si no existe (→ `vuelo_no_disponible`). |
| `precio_vigente(db, vuelo_id, clase, *, ahora=None) -> PrecioVigente` | reservas: el precio que se congela al reservar o iniciar la compra (RF-24). |
| `nombre_de_silla(tipo, clase, numero) -> str` | reservas: `18C` a partir del número interno (SUP-26). |
| `marcar_promociones_agotadas(db, vuelo_id, *, ahora=None) -> list[int]` | reservas: al **vender** la última silla de una clase (confirmar una compra o pagar una reserva), no al reservar ni al bloquear: una reserva o un bloqueo que vencen devolverían la silla, pero `agotada` es un estado final (RF-23). |

### `reservas.service` · dueño: Backend B · la llaman vuelos, usuarios y carrito

Ya existe desde #138 (modelo, consultas y reglas de los viajeros); #118 completa `anular_reservas_de_vuelo`. Las consultas de la iteración 1 conservan su firma y ya consultan datos reales. El modelo (`reservas.models`) tiene `Transaccion` (reserva o compra), `Tramo` (vuelo, clase y precio congelado), `Viajero` y `Tiquete` (silla y estado); la base de datos impide dos tiquetes activos en la misma silla o con el mismo documento en un vuelo (RF-34, RF-42). Un tiquete está **activo** si es `bloqueado`, `reservado` o `comprado`.

| Función | Comportamiento |
|---|---|
| `ocupacion_de_vuelos(db, vuelo_ids) -> dict[int, OcupacionVuelo]` | `vendidas_*`: tiquetes `comprado`. `reservadas_*`: tiquetes `reservado` y `bloqueado` (de reservas vigentes y de compras pendientes), para que vuelos y búsqueda los descuenten de `disponibles`. `reservas_activas`: hoy cuenta solo las reservas `vigente`; para cumplir este contrato también debe contar las compras `pendiente` (sus sillas bloqueadas impiden editar el vuelo, HU-15): lo ajusta #124. Lo vencido, cancelado, reembolsado o reubicado no cuenta. |
| `anular_reservas_de_vuelo(db, vuelo_id) -> int` | Hoy devuelve 0: #118 lo implementa. Reservas vigentes → `cancelada` y compras pendientes → `cancelada`; sus tiquetes pasan a `cancelado`, libera las sillas y encola el correo a cada cliente. Devuelve cuántas anuló, contando ambas (cuadra con `reservas_activas`). |
| `pasajeros_de_vuelo(db, vuelo_id) -> list[PasajeroVuelo]` | Viajeros con tiquete `comprado`, ordenados por silla. Una reserva o un bloqueo todavía no es un pasajero. |
| `tiquetes_activos_futuros_de_cliente(db, usuario_id) -> list[TiqueteActivo]` | Una entrada por transacción y vuelo con tiquetes activos del cliente (reservas vigentes, compras activas y compras pendientes) en vuelos que no han salido. `codigo_reserva` es `str | None` por el modelo, pero desde #118 y #124 toda reserva y compra tiene código. |
| `tiquetes_activos_en_vuelo(db, usuario_id, vuelo_id) -> int` | Tiquetes activos del cliente en el vuelo (reservados, comprados y bloqueados; RF-32, SUP-09). Lo vencido o cancelado no cuenta. Lo usa carrito para el límite de 5. |

Reglas de los viajeros, que usan #118, #124 y #130 al reservar y comprar, y el carrito (#126) para el límite y el cupo. Cada una lanza un error del formato único y ninguna hace commit:

```python
MAXIMO_TIQUETES_POR_VUELO = 5  # RF-32; saldrá de la configuración (RNF-23)


@dataclass(frozen=True)
class ViajeroParaValidar:
    """Datos de un viajero para las reglas RF-31 a RF-35: la forma de entrada del service, que
    #118 y #124 arman a partir de `ViajeroEntrada`."""

    tipo_documento: str
    numero_documento: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None
    genero: str
    telefono: str
    email: str
    contacto_nombre: str
    contacto_telefono: str


def validar_viajeros(viajeros: Sequence[ViajeroParaValidar], *, hoy: date | None = None) -> None:
    """RF-31: DatosInvalidos (422 datos_invalidos) con `campos["viajeros.N.<campo>"]` si falta un
    campo obligatorio, el correo no tiene formato válido, el género no es una opción o la fecha de
    nacimiento no pasa `usuarios.service.validar_fecha_nacimiento` (SUP-43)."""


def validar_limite_de_tiquetes(db: Session, usuario_id: int, vuelo_id: int, cantidad: int) -> None:
    """RF-32: LimiteDeTiquetes (409 limite_tiquetes) si los tiquetes activos del cliente en el
    vuelo + `cantidad` superan MAXIMO_TIQUETES_POR_VUELO."""


def validar_cupo(db: Session, vuelo_id: int, clase: Clase, cantidad: int) -> None:
    """RF-33: SillasInsuficientes (409 clase_agotada) si `cantidad` supera las sillas disponibles
    de esa clase, aunque la otra tenga. Usa vuelos.service.obtener_vuelo_detalle."""


def validar_documentos_en_vuelo(
    db: Session, vuelo_id: int, viajeros: Sequence[ViajeroParaValidar]
) -> None:
    """RF-34: ViajeroDuplicado (409 viajero_duplicado) con
    `campos["viajeros.N.numero_documento"]` si un documento tiene un tiquete activo en el vuelo,
    de este o de otro cliente, o está repetido en `viajeros`. No revela quién tiene el otro."""


def validar_menores(db: Session, vuelo_id: int, viajeros: Sequence[ViajeroParaValidar]) -> None:
    """RF-35: MenorSinAdulto (422 menor_sin_adulto) con `campos["viajeros.N.fecha_nacimiento"]`
    en cada menor si ninguno de `viajeros` tiene 18 años el día de la salida (hora local del
    origen)."""
```

| Excepción | HTTP y `codigo` | Mensaje |
|---|---|---|
| `LimiteDeTiquetes(Conflicto)` | 409 `limite_tiquetes` | «Un cliente puede tener máximo 5 tiquetes activos en el mismo vuelo.» |
| `ViajeroDuplicado(Conflicto)` | 409 `viajero_duplicado` | «Uno de los documentos ya tiene un tiquete activo en este vuelo.» |
| `MenorSinAdulto(DatosInvalidos)` | 422 `menor_sin_adulto` | «Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.» |
| `SillasInsuficientes(Conflicto)` (en `reservas.sillas`) | 409 `clase_agotada` | «No quedan sillas suficientes en esta clase.» |

Lo que el modelo de #138 deja resuelto para #118, #124 y #131, sin cambiar el contrato:

- `transacciones.codigo` es `unique` y admite `null`. Reservas y compras directas guardan su código al crearse. Para que la compra de una reserva conserve su código (HU-27), #131 necesita relajar esa restricción en su migración (por ejemplo, única por `codigo` y `tipo`) o modelar el pago sin crear otra fila; el contrato fija lo que ve el cliente, no la tabla.
- `Viaje.vence_en` sale de `transacciones.vence_en` en una reserva y de `bloqueo_hasta` en una compra pendiente o vencida.
- El modelo guarda un `Tramo` por vuelo y clase (`orden` 1 o 2); `Viaje.tramos` trae uno por vuelo y cada tiquete de `viajeros[].tiquetes` lleva su clase y su precio.

### `reservas.sillas` · ya existe desde #137 · lo llaman las reservas y las compras (#118, #124, #130) y la reubicación (iteración 3)

```python
TipoVuelo = Literal["nacional", "internacional"]
Clase = Literal["economica", "primera"]
MAXIMO_POR_CLASE = 5  # RF-41: k viajeros de una misma transacción y clase, 1 ≤ k ≤ 5


class SillasInsuficientes(Conflicto):
    codigo = "clase_agotada"
    mensaje = "No quedan sillas suficientes en esta clase."


def asignar_sillas(
    tipo: TipoVuelo,
    clase: Clase,
    ocupadas: Collection[int],
    cantidad: int,
    rng: random.Random,
) -> list[int]:
    """Números internos de `cantidad` sillas libres de la clase, con el algoritmo de RF-41 y la
    distribución del Apéndice A, ordenados de menor a mayor. Lanza SillasInsuficientes si no
    alcanzan y ValueError si `cantidad` no está entre 1 y 5. Función pura."""
```

`ocupadas` son los números de silla de los tiquetes activos del vuelo; en producción `rng` es `random.SystemRandom()`.

### `reservas.comprobante` · #117 · lo llaman la compra (#124) y el pago de reservas (#131)

```python
@dataclass(frozen=True)
class TramoComprobante:
    vuelo_codigo: str
    origen: str               # nombre de la ciudad
    destino: str
    salida: datetime          # UTC
    zona_origen: str          # IANA, para la hora local de salida
    llegada: datetime         # UTC
    zona_destino: str


@dataclass(frozen=True)
class TiqueteComprobante:
    tramo: int                # índice en DatosComprobante.tramos
    clase: Literal["economica", "primera"]
    silla: str                # "18C"
    precio: int               # COP


@dataclass(frozen=True)
class ViajeroComprobante:
    nombres: str
    apellidos: str
    tipo_documento: str
    numero_documento: str
    tiquetes: tuple[TiqueteComprobante, ...]


@dataclass(frozen=True)
class DatosComprobante:
    codigo: str
    comprador: str            # nombres y apellidos del cliente
    pagado_en: datetime       # UTC
    tramos: tuple[TramoComprobante, ...]
    viajeros: tuple[ViajeroComprobante, ...]   # solo los pagados en esta operación
    total: int                # lo pagado en esta operación


def generar_comprobante(datos: DatosComprobante) -> bytes:
    """PDF del comprobante de compra (RF-39 c): código, vuelos con su salida en hora local,
    viajeros con su clase y silla, valor de cada tiquete y total en COP. Español de Colombia,
    fechas dd/mm/aaaa y horas de 24 h. Función pura: no consulta la base de datos."""
```

### `monedero.service` · dueño: Backend A · #115 · la llama reservas

```python
class SaldoInsuficiente(Conflicto):
    codigo = "saldo_insuficiente"


@dataclass(frozen=True)
class MovimientoMonedero:
    id: int
    tipo: Literal["recarga", "compra", "reembolso"]
    valor: int                # con signo
    saldo_resultante: int
    referencia: str
    creado_en: datetime


def saldo_de(db: Session, usuario_id: int) -> int:
    """Saldo del cliente: la suma de sus movimientos, 0 si no tiene (RF-48)."""


def debitar(db: Session, usuario_id: int, valor: int, *, referencia: str) -> MovimientoMonedero:
    """Registra un movimiento `compra` por -valor con su saldo resultante (RF-39). `valor` > 0.

    Bloquea el saldo del cliente (SELECT … FOR UPDATE) para que dos compras simultáneas no lo
    dejen negativo. Si no alcanza, lanza SaldoInsuficiente («Tu saldo no alcanza: te faltan
    $ 300.000.») sin registrar nada. No hace commit."""


def acreditar(db: Session, usuario_id: int, valor: int, *, referencia: str) -> MovimientoMonedero:
    """Registra un movimiento `reembolso` por +valor (iteración 3). `valor` > 0. No hace commit."""
```

### `usuarios.service` · dueño: Backend A · ya existen · las llama reservas

| Función | Para qué |
|---|---|
| `obtener_perfil(db, usuario_id) -> PerfilSalida` | `email_verificado` (HU-02), el nombre y el correo del comprador para el comprobante. |
| `validar_fecha_nacimiento(fecha, hoy) -> None` | Fecha de nacimiento de cada viajero (SUP-43); el error se reubica en `viajeros.N.fecha_nacimiento`. |

### `core.mail` · #116 · lo llama reservas

```python
@dataclass(frozen=True)
class Adjunto:
    nombre: str        # "comprobante-K7Q2MX.pdf"
    tipo_mime: str     # "application/pdf"
    contenido: bytes


def encolar_correo(
    db: Session,
    destinatario: str,
    asunto: str,
    texto: str,
    html: str | None = None,
    adjuntos: Sequence[Adjunto] = (),
) -> int:
    """Como hoy, más los adjuntos: se guardan con core/archivos.py y la cola guarda solo la
    referencia. Si la transacción de quien encola se revierte, el correo no sale."""
```

### Procesos programados nuevos

| Tarea | Issue | Qué hace |
|---|---|---|
| `reservas.vencer_reservas` | #118 | Reservas vigentes con `vence_en` ≤ `ahora` → `vencida`, sillas libres, correo al cliente (RF-37). |
| `reservas.liberar_bloqueos` | #124 | Compras pendientes con el bloqueo vencido (`bloqueo_hasta` ≤ `ahora`) → `vencida`, tiquetes `vencido`, sillas libres (SUP-15). |

Ambas cada minuto, idempotentes y sin commit, como dice `AGENTS.md`.

## Pendientes de infraestructura

Necesitan un issue del líder porque tocan `core/`, Docker o recursos compartidos:

1. **Parametrización (RNF-23).** La vigencia de la reserva (24 h), los límites de venta y cancelación (1 h y 3 h), el máximo de tiquetes por vuelo (5) y el bloqueo de la compra (15 min) deben leerse de `core/config.py`. Mientras tanto, cada módulo los declara como constantes con nombre (`VIGENCIA_RESERVA`, `LIMITE_VENTA`, `MAXIMO_TIQUETES_POR_VUELO`, `BLOQUEO_COMPRA`; esta última ya existe en `reservas.service`) para que el cambio sea de una línea, y los schemas no los repiten.
2. **Adjuntos en la cola de correos y librería de PDF.** #116.
3. **Fixture con datos confirmados** para la prueba de 50 compras simultáneas. #129.
4. **Prueba de carga de la búsqueda** con un servicio de Compose de perfil `carga`. #135.
5. **Códigos de error repetidos.** `rango_invalido`, `clase_agotada` y los demás se lanzan con las excepciones de `core` y `codigo=` propio (`DatosInvalidos("…", codigo="rango_invalido", campos=…)`) o con una subclase en el módulo. Si varios módulos repiten la misma subclase, puede subir a `core/errors.py`.

## Decisiones de este contrato

Puntos que el SRS y las HU dejan abiertos y que este contrato fija. Si alguno cambia, se cambia aquí, en el `schemas.py`, en los mocks y en los issues que lo citan:

- La clase va por viajero y por tramo (`viajeros[i].clases[j]`), aunque la selección del carrito traiga una clase por tramo: esa es solo el valor inicial de cada viajero (RF-33, HU-26).
- Un trayecto completo es una lista `tramos` de dos elementos, ida y regreso, con un solo código. Su reserva vence en el límite más próximo de sus dos vuelos (o a las 24 horas, si llega antes) y su bloqueo de compra a los 15 minutos o en ese mismo límite.
- El límite de venta es el mismo límite de cancelación (1 h nacional, 3 h internacional) y aplica a búsqueda, carrito, reserva y compra.
- Una reserva tiene código desde que se crea y una compra directa desde que se inicia. Pagar una reserva, toda o por partes, conserva su código: los pagos de una misma reserva se acumulan en una sola compra con ese código.
- El carrito recalcula cada selección en cada lectura y la marca con avisos: el cambio de precio advierte pero deja confirmar; la falta de cupo, el límite de 5 o un vuelo que ya no se vende impiden confirmar. Modificar la selección renueva su precio de referencia.
- Los rangos de fecha y hora de la búsqueda son locales del origen de cada vuelo; los de Mis viajes y los movimientos, de Colombia.
- La recarga recibe `faltante`, `codigo` y `volver` por la URL y vuelve a la compra o a Mis viajes.
- El frontend quita la selección del carrito después de reservar o de confirmar la compra; el backend de reservas no conoce el carrito.
- La compra va en dos pasos: iniciar bloquea las sillas 15 minutos y confirmar cobra. La competencia por las sillas se resuelve al bloquear; confirmar no reasigna.
- Las sillas bloqueadas cuentan como ocupadas, como tiquetes activos y como reservas activas del vuelo.
- Lo que vence se informa vencido a su hora, aunque el proceso automático no haya corrido.
- `regresos` solo devuelve los regresos elegibles.
- Sin `clase`, la búsqueda filtra y ordena por el menor precio vigente del vuelo.
- La búsqueda registra solo la primera página de cada búsqueda de un cliente.
- Todos los datos del viajero son obligatorios, incluidos el teléfono y el correo (RF-31): así el código llega a cada viajero. Es lo que valida `reservas.service.validar_viajeros` y lo que guarda el modelo.
- La franquicia de la tarjeta se deduce del número y el vencimiento viaja como `MM/AA`. Las tarjetas vencidas se listan marcadas y no sirven para recargar.
- Los movimientos llevan signo y el saldo es su suma. La recarga no tiene tope de negocio, solo uno técnico de un billón de pesos.
- `marcar_promociones_agotadas` se llama al vender la última silla, no al reservarla ni al bloquearla.
- Los topes de negocio (5, 24 h, 15 min, 1 h, 3 h) no van en los schemas, para poder configurarlos (RNF-23).

## Mocks para el frontend

`frontend/src/mocks/` simula toda la API de esta iteración con MSW, igual que en la [iteración 1](iteracion-1.md#mocks-para-el-frontend): datos tipados con `src/api/schema.d.ts`, handlers con `openapi-msw` y las reglas justas para ver cada estado de las pantallas. Se activan con `VITE_API_MOCK=true` en el `.env` y `docker compose up -d frontend`.

- Lo que se crea o cambia dura hasta recargar la página. La reserva vigente H4N8WQ vence 21 horas después de cargar los mocks y la compra pendiente K7Q2PX 15 minutos después.
- Los vuelos de la iteración 2 salen en abril de 2027, para que sigan a la venta todo el semestre. Las horas de esta sección son locales del origen.

Usuarios de prueba (contraseña `Clave1234`), además de los de la iteración 1:

| Usuario | Para probar |
|---|---|
| `lauragomez` | Cliente verificado con saldo de $ 1.000.000, tres tarjetas (una vencida), siete movimientos, un carrito con tres selecciones, reservas vigentes y vencida, compras activas, una compra pendiente y una vencida, y 5 tiquetes activos en STA-00135. |
| `sofiamarin` | Cliente verificado sin saldo, sin tarjetas, sin movimientos, con el carrito vacío y sin viajes. |
| `pedrorios` | Cliente sin verificar: reservar, comprar y pagar responden `correo_no_verificado`. |
| `cruiz`, `root` | Buscan como cualquiera (la búsqueda es pública); carrito, reservas, Mis viajes y monedero responden `403`. |

Vuelos:

| Vuelo | Ruta y salida | Económica / primera | Para probar |
|---|---|---|---|
| STA-00131 | Pereira → Bogotá, 15/04/2027 06:00 | $ 262.500, hoy $ 210.000 con 20 % de promoción / $ 690.000 | Promoción y cambio de precio en el carrito. Quedan 12 en económica y 4 en primera. Los documentos CC 1088345921 y CC 42118907 ya tienen tiquete activo: `viajero_duplicado`. |
| STA-00135 | Pereira → Cartagena, 18/04/2027 10:00 | $ 300.000 / $ 850.000 | `lauragomez` tiene 3 tiquetes comprados y 2 reservados: `limite_tiquetes`. |
| STA-00142 | Pereira → Medellín, 15/04/2027 07:40 | $ 185.000 / $ 520.000 | Vuelo libre para reservar y comprar. |
| STA-00157 | Pereira → Cartagena, 15/04/2027 09:15 | $ 320.000 / $ 890.000 | Económica agotada. |
| STA-00158 | Pereira → Bogotá, 15/04/2027 18:00 | $ 240.000 / $ 690.000 | Primera agotada. |
| STA-00159 | Pereira → Medellín, 15/04/2027 12:00 | $ 230.000 / $ 610.000 | Queda una sola silla en económica: 1 viajero sí, 2 no. |
| STA-00160 | Pereira → Cartagena, 20/04/2027 09:15 | $ 400.000 / $ 950.000 | Compra pendiente K7Q2PX con las sillas 18C y 18D bloqueadas. |
| STA-00101 | Pereira → Nueva York, 15/04/2027 08:00 (llega 14:30 hora de Nueva York) | $ 1.650.000 / $ 4.100.000 | Ida del trayecto completo. Con `lauragomez`, comprarla en primera da `saldo_insuficiente` (faltan $ 3.100.000). |
| STA-00104 | Pereira → Nueva York, 15/04/2027 23:10 | $ 1.450.000 / $ 3.650.000 | Llega el 16/04: no tiene regresos el 15/04. |
| STA-00129 | Nueva York → Cartagena, 15/04/2027 06:30 | $ 1.620.000 / $ 3.800.000 | Sale antes de la llegada de STA-00101: nunca es su regreso (`regreso_invalido` si se fuerza). |
| STA-00133 | Nueva York → Cartagena, 15/04/2027 20:00 | $ 1.580.000 / $ 3.700.000 | Regreso el mismo día de STA-00101. |
| STA-00132 | Nueva York → Cartagena, 22/04/2027 10:00 | $ 1.750.000 / $ 3.900.000 | Regreso del ejemplo Pereira → Nueva York → Cartagena. |

Siguen los de la iteración 1: STA-00044 está cancelado (`vuelo_no_disponible`) y STA-00076 ya salió (`fuera_de_plazo`).

Viajes de `lauragomez`:

| Código | Id y estado | Vuelo | Viajeros (id) | Para probar |
|---|---|---|---|---|
| H4N8WQ | Reserva 41, vigente | STA-00131, económica, $ 262.500 congelado | Laura Gómez (4101), Marta Ríos (4102), Tomás Gómez, 14 años (4103) | Pagar completa o por viajero al precio congelado; pagar solo a Tomás da `menor_sin_adulto`. |
| R5T2LM | Reserva 43, vigente | STA-00135, económica | Camilo Ríos (4301), Lucía Ríos (4302) | Cuenta para el límite de 5. |
| B3M9TA | Reserva 42, vencida | STA-00142 | Laura Gómez (4201) | Pagarla da `reserva_no_vigente`. |
| K7Q2PX | Compra 901, pendiente | STA-00160, 2 × $ 400.000 | Laura Gómez, Marta Ríos | `/compra/pago/901`: confirmar deja el saldo en $ 200.000. |
| Z9Y8X7 | Compra 902, vencida | STA-00142 | Laura Gómez, Marta Ríos | `/compra/pago/902`: confirmar da `bloqueo_vencido`. |
| K7Q2MX | Compra 903, activa | STA-00088 (Bogotá → Madrid), económica | Laura Gómez, Jorge Gómez | Es el bloqueo de HU-09. |
| P3X7KD | Compra 904, activa | STA-00135, económica | Laura Gómez, Jorge Gómez, Ana Gómez | Límite de 5. |

Carrito de `lauragomez`: selección 71 (STA-00131 económica, 2 viajeros, agregada a $ 262.500: aviso `precio_cambio`, confirmable), 72 (STA-00157 económica, 2 viajeros: aviso `clase_agotada`, no confirmable) y 73 (STA-00101 en primera + STA-00132 en económica, 2 viajeros: trayecto completo de $ 11.700.000).

Monedero de `lauragomez`: tarjetas 21 (crédito Visa **** 4242, 08/28), 22 (débito Mastercard **** 5100, 01/27) y 23 (crédito Visa **** 1111, 05/26, vencida). Movimientos: dos recargas de $ 500.000, una compra y su reembolso de $ 185.000 (Q8W2RT), una recarga de $ 5.800.000 y las compras K7Q2MX ($ 4.900.000) y P3X7KD ($ 900.000): saldo $ 1.000.000.

Otros valores que disparan errores:

- Búsqueda: `precio_min` mayor que `precio_max`, o `fecha_hasta`, `hora_hasta` o `duracion_max` menores que su inicio → `rango_invalido`. Regresos de STA-00101 con fecha 14/04/2027 → `rango_invalido`; `vuelo_ida_id=9999` → `404`.
- Viajeros: un único viajero nacido el 02/05/2012 → `menor_sin_adulto`; nacido el 14/04/2009 cumple 18 el 14/04/2027 y puede viajar solo el 15/04; nacido el 16/04/2009, no.
- Tarjetas: `4242424242424241` → `tarjeta_invalida`; un vencimiento anterior al mes actual (p. ej. `05/26`) → `tarjeta_vencida`; recargar con la tarjeta 23 → `tarjeta_vencida`; `valor` 0 → `datos_invalidos`. Números válidos: `4242424242424242` (Visa), `5555555555554444` (Mastercard) y `378282246310005` (American Express).
