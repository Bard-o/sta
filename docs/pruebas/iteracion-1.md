# Prueba integral · Iteración 1

Recorrido de cada criterio de aceptación de HU-01 a HU-19 en la aplicación completa, sin mocks (issue [#48](https://github.com/Bard-o/sta/issues/48)). Fecha: 23/10/2026.

Entorno: `main` en `076ad0b`, `docker compose up -d --build`, `VITE_API_MOCK` sin definir (API real), base de datos vacía salvo el root. Cada criterio se probó contra la API (script con `requests` y la bandeja de Mailpit) y en la interfaz desde el navegador. Los criterios que dependen de reservas o compras quedan para la iteración 2, porque hoy no hay forma de crear una reserva.

Leyenda: ✅ cumple · ❌ falla (con su issue) · ⏭️ no se puede probar todavía (iteración 2)

**Resultado:** un fallo, [#94](https://github.com/Bard-o/sta/issues/94) (@pandi-5), resuelto en [#95](https://github.com/Bard-o/sta/pull/95) y verificado de nuevo en `35e22ca` (ver abajo). Todo lo demás cumple.

- ✅ `npm run gen:api` no produce diferencias con `src/api/schema.d.ts`.

## HU-01 Registrarse como cliente
- ✅ Registro válido crea la cuenta (sin verificar), inicia la sesión y envía el enlace de verificación. API e interfaz.
- ✅ Sin aceptar la política: rechazado (`campos.acepta_politica`). API e interfaz.
- ✅ Fecha de nacimiento futura, correo mal formado y contraseña corta, solo letras o solo números: rechazados con el campo marcado. API e interfaz.
- ✅ Documento, correo o usuario repetidos, también con otras mayúsculas: `409` con el campo. La interfaz marca el correo duplicado.
- ✅ Un menor de edad (RC, 2020; y 2010 por la interfaz) se registra.
- ✅ Extra: imagen PNG aceptada; GIF y archivos de más de 2 MB rechazados (`campos.imagen`); registrarse con una sesión abierta responde `403`.

## HU-02 Verificar correo electrónico
- ✅ Un enlace vigente verifica el correo sin sesión y habilita la suscripción. API e interfaz.
- ✅ Un enlace usado o inválido muestra el error y el botón «Enviar un enlace nuevo». API e interfaz.
- ✅ Al reenviar, el enlace anterior deja de funcionar. API e interfaz.
- ⏭️ Redirigir a la verificación al reservar o comprar sin verificar: iteración 2. La suscripción sí se bloquea con `403 correo_no_verificado`.

## HU-03 Iniciar sesión
- ✅ Con usuario, correo o usuario en mayúsculas se entra al inicio del rol (`/cliente`, `/admin`, `/root`).
- ✅ Usuario inexistente y contraseña errada dan el mismo `401` «Usuario o contraseña incorrectos.».
- ✅ Tras 5 fallos, el sexto con la contraseña correcta responde `429`, con `Retry-After` y «Cuenta bloqueada. Intenta de nuevo en N minutos.» en la interfaz.
- ✅ Una cuenta desactivada recibe «Cuenta inactiva.». API e interfaz.
- ✅ Inactividad: un token vencido responde `401`. Los tokens duran 30 min para cliente y 15 min para root y admin.
- ⏭️ Admin o root que reserva o compra: los endpoints llegan en la iteración 2. Con los endpoints de la iteración 1 la matriz de roles responde `403 sin_permiso` donde debe.

## HU-04 Cerrar sesión
- ✅ Tras cerrar sesión se muestra el inicio público.
- ✅ La cookie anterior responde `401` (se invalida en el servidor) y una ruta protegida lleva a `/login?next=…`.

## HU-05 Restablecer contraseña
- ✅ Mismo mensaje `202` exista o no el correo. API e interfaz.
- ✅ Llega el enlace y la contraseña nueva se valida (política y confirmación). Si el correo es de un cliente y de un admin, llega un enlace por cada cuenta, con su usuario.
- ✅ Un enlace usado muestra el error y «Pedir un enlace nuevo». API e interfaz.
- ✅ Tras restablecer se cierran todas las sesiones y la contraseña anterior deja de funcionar.
- ✅ El correo no incluye la contraseña.

## HU-06 Cambiar contraseña
- ✅ El cambio válido se guarda, la contraseña anterior deja de funcionar y la sesión sigue abierta. API e interfaz.
- ✅ Con la contraseña actual incorrecta no cambia nada. API e interfaz.
- ✅ Una contraseña nueva fuera de política o que no coincide se rechaza con el motivo. API e interfaz.
- ✅ El root solo ve «Mi cuenta» con el cambio de contraseña.

## HU-07 Editar perfil
- ✅ Al volver a abrir el perfil se ven los datos actualizados, también la suscripción a noticias (antes ❌ [#94](https://github.com/Bard-o/sta/issues/94), resuelto en [#95](https://github.com/Bard-o/sta/pull/95)).
- ✅ Documento y usuario son de solo lectura. La API ignora esos campos si se envían.
- ✅ Al cambiar el correo llega el enlace al correo nuevo, el anterior sigue siendo el de la cuenta (no sirve para entrar con el nuevo) y la interfaz avisa «Pendiente de verificar».
- ✅ Un correo de otra cuenta cliente se rechaza (`409 campos.email`).

## HU-08 Suscribirse a noticias
- ✅ El suscrito recibe un correo por cada noticia (17 de 17) en menos de 1 minuto.
- ✅ El no suscrito no recibe ninguno.
- ✅ El enlace «cancelar suscripción» del correo da de baja sin sesión. API y página `/noticias/baja`.
- ✅ Sin verificar no puede suscribirse (`403 correo_no_verificado`) y se le ofrece verificar.
- ✅ Tras suscribirse o darse de baja, al recargar `/perfil` el interruptor conserva su estado (antes ❌ [#94](https://github.com/Bard-o/sta/issues/94), resuelto en [#95](https://github.com/Bard-o/sta/pull/95)).

## HU-09 Desactivar cuenta
- ✅ Tras confirmar se cierra la sesión (también en otros dispositivos) y el login responde «Cuenta inactiva.». API e interfaz.
- ✅ La fila sigue en `usuarios` con `activo = false` y sus datos.
- ⏭️ Bloqueo por reservas o tiquetes activos: iteración 2. `GET /me/desactivacion` hoy responde `puede_desactivar: true`.

## HU-10 Crear administrador
- ✅ El root crea un administrador, queda en «Registro incompleto» y la creación va a la auditoría sin la contraseña. API e interfaz.
- ✅ Un usuario existente (otro admin, un cliente, `root`, con otras mayúsculas) se rechaza. API e interfaz.
- ✅ Un cliente o un admin que crea, lista o desactiva administradores recibe `403`; sin sesión, `401`.
- ✅ Ningún endpoint crea un root: enviar `"rol": "root"` crea un administrador normal.

## HU-11 Desactivar o reactivar administrador
- ✅ El admin desactivado recibe «Cuenta inactiva.» y se cierran sus sesiones. Hay diálogo de confirmación.
- ✅ Al reactivarlo puede volver a entrar. Uno con el registro incompleto vuelve a «Registro incompleto».
- ✅ La lista muestra Activo, Inactivo y Registro incompleto. Desactivar y reactivar se auditan con el estado anterior y el nuevo.

## HU-12 Completar registro de administrador
- ✅ Con el registro incompleto, cualquier ruta (`/admin/vuelos`) lleva a `/admin/primer-ingreso`, y la API responde `403 registro_incompleto`.
- ✅ Al completarlo, la contraseña temporal deja de funcionar y aparece el menú de administrador. API e interfaz.
- ✅ El mismo documento y el mismo correo sirven para una cuenta cliente, en los dos órdenes, con otro usuario. Entre administradores se rechazan.

## HU-13 Programar vuelo
- ✅ Pereira → Madrid y Madrid → Cartagena se aceptan. Manizales → Miami y Madrid → Londres responden `ruta_no_permitida`, y la interfaz explica por qué.
- ✅ Salida pasada, duración 0 o de 24 h, y precio 0 o negativo: rechazados con el campo. 23 h 59 min se acepta.
- ✅ Pereira → Bogotá a las 06:00: otro a la misma hora se rechaza y a las 06:20 se acepta. API e interfaz.
- ✅ Bogotá → Madrid a las 22:00 con 10 h llega el 11/12/2026 a las 14:00 (UTC+1). Para el horario de verano usé el 10/07/**2027**, porque el 10/07/2026 ya pasó: llega el 11/07/2027 a las 15:00 (UTC+2), también en la vista previa.
- ✅ Pereira → Miami genera su noticia y su elemento del carrusel con `MIA.jpg`, y la imagen se sirve. Capacidades 25 + 125 y 50 + 200. Código `STA-nnnnn`. Creación auditada.

## HU-14 Programar vuelos recurrentes
- ✅ «Todos los lunes 06:00 Pereira → Bogotá, octubre a diciembre de 2026» crea un vuelo por cada lunes futuro (9). Omite tres por pasados y uno por duplicado.
- ✅ Un periodo de más de 12 meses, o con fin antes del inicio, se rechaza. La interfaz marca «Hasta».
- ✅ Editar una ocurrencia y cancelar otra no cambia las demás.
- ✅ El resumen lista los vuelos creados y las fechas omitidas con su motivo. API e interfaz.

## HU-15 Editar vuelo
- ⏭️ Bloqueo con reservas o compras, y vuelve a ser editable al vencer la reserva: iteración 2.
- ✅ Editar el precio deja en la auditoría el precio anterior y el nuevo, y la noticia se actualiza.
- ✅ Un vuelo realizado, cancelado o que ya despegó no se edita (`vuelo_cerrado`). La interfaz deshabilita «Editar» con «El vuelo ya salió.».
- ✅ Extra: cambiar la ruta recalcula el tipo y la capacidad y conserva el código. Se vuelven a aplicar las reglas de unicidad y de ruta. Los filtros por código, ciudad y fechas funcionan.

## HU-16 Cancelar vuelo sin ventas
- ✅ Tras cancelar sale del carrusel y su noticia queda no vigente. El detalle avisa «Este vuelo fue cancelado». La búsqueda llega en la iteración 2.
- ⏭️ Correo de anulación a cada cliente con reserva: iteración 2. Hoy `reservas_anuladas` es 0 y el diálogo dice «No tiene reservas activas.».
- ✅ Cancelar un vuelo realizado, uno que ya despegó o uno ya cancelado: `vuelo_cerrado`.
- ⏭️ Vuelo con tiquetes vendidos: iteración 2.
- ✅ Extra: la cancelación se audita y el código no se reutiliza.

## HU-17 Crear promoción
- ✅ Durante la vigencia, el detalle y la noticia muestran el precio con el descuento redondeado hacia abajo (2.450.000 − 30 % = 1.715.000) y la etiqueta de promoción. La búsqueda llega en la iteración 2.
- ✅ Una segunda promoción para la misma clase se rechaza (`promocion_duplicada`); para la otra clase se acepta como programada. API e interfaz.
- ⏭️ «Agotada» al venderse la última silla: iteración 2.
- ✅ No se crea promoción para un vuelo cancelado, realizado o que ya despegó.
- ⏭️ Ninguna devolución a tiquetes comprados antes: iteración 2.
- ✅ Extra: porcentajes 0 y 95 rechazados; la promoción va primero en el carrusel, aparece en `/admin/promociones` y se audita.

## HU-18 Consultar vuelos realizados
- ✅ Llegadas a las 05:29 y 05:30 UTC: ambos vuelos pasaron a realizado a los 36 s y salieron del carrusel.
- ✅ Con el backend apagado durante la llegada (05:33), el vuelo quedó realizado al arrancar (05:33:26).
- ✅ El detalle muestra la ocupación por clase y la lista de pasajeros, vacía hasta la iteración 2. Los filtros por código, ruta y fecha funcionan.

## HU-19 Consultar noticias y carrusel
- ✅ Un visitante sin sesión ve el listado y el carrusel.
- ✅ Una noticia y «Ver vuelo» del carrusel abren `/vuelos/:id`.
- ✅ Una promoción vencida (fin a las 05:27:17) quedó no vigente y fuera del carrusel a las 05:27:20, y el precio volvió al base. «Agotada» llega en la iteración 2.
- ✅ Con 17 elementos posibles, el carrusel muestra 10: primero las promociones, luego los vuelos del más reciente al más antiguo, sin repetir vuelo.
- ✅ No hay interfaz para crear noticias. `POST`, `PUT`, `PATCH` y `DELETE` sobre `/noticias` responden `405`.

## Reverificación tras [#95](https://github.com/Bard-o/sta/pull/95) · `main` en `35e22ca`
- ✅ [#94](https://github.com/Bard-o/sta/issues/94): `GET /usuarios/me/perfil` devuelve `suscrito_noticias: true` tras suscribirse, y `false` tras darse de baja desde el perfil o con el enlace del correo. Para el administrador sigue en `false`.
- ✅ [#94](https://github.com/Bard-o/sta/issues/94) en la interfaz: el interruptor de `/perfil` conserva su estado al recargar, encendido y apagado.
- ✅ Backend: `pytest` (787 pasan), `ruff check` y `ruff format --check`.
- ✅ Frontend: `npm test` (339 pasan), `npm run lint` y `npm run typecheck`.
- ✅ `npm run gen:api` sigue sin producir diferencias.

## Observaciones (no incumplen ningún criterio; el dueño decide si abre issue)
- **Vuelo ya despegado en el carrusel:** sigue como vigente hasta que llega, porque el contrato define vigente como «programado». No se puede comprar, así que conviene sacarlo al salir (vuelos y noticias).
- **Enlace «Promoción» en un vuelo ya despegado:** en `/admin/vuelos` sigue activo aunque «Editar» se deshabilita; la API lo rechaza igual (frontend).
- **Formato de fechas y horas en los formularios:** los `input type="date"`, `time` y `datetime-local` siguen el idioma del navegador. En un navegador en inglés muestran `mm/dd/yyyy` y `10:00 PM`, lo que choca con IU-05 (frontend).
- **Saludo del inicio del rol:** dice «Hola, anainterfaz» con el nombre de usuario, aunque el menú ya muestra «Ana Interfaz».
- **Cerrar sesión cierra todas las sesiones del usuario:** el logout cierra también las de otros dispositivos. HU-04 no lo prohíbe; lo dejo anotado.
