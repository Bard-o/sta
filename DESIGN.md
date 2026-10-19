# AVIANCO — Sistema de diseño del STA

> Fuente de verdad visual del frontend del Sistema de Tiquetes Aéreos (STA). Léelo antes de crear o modificar cualquier pantalla o componente. Los valores exactos viven en `design/tokens.json`; este archivo dice cómo usarlos.

## Archivos del sistema de diseño

| Archivo | Qué es | Cómo usarlo |
|---|---|---|
| `DESIGN.md` | Este documento: reglas de marca, voz, color, tipografía y componentes | Leer primero |
| `design/tokens.json` | Fuente única de colores (temas Noche y Día), tipografía, espacio, radios, sombras y blur | Si cambias un valor, cámbialo aquí y regenera `tokens.css` con `npm run tokens` |
| `design/tokens.css` | Generado desde `tokens.json`: los tokens como variables CSS (`--glass`, `--accent`, `--space-4`…) y clases de texto (`.title-lg`, `.caption`…) | No se edita a mano. Importar una vez en `src/main.tsx` |
| `design/build-tokens.mjs` | Generador de `tokens.css` (Node, sin dependencias); con `--check` falla si `tokens.css` está desactualizado | Lo corre `npm run tokens` |
| `design/components.css` | Estilos de todos los componentes, clases `sta-*`; solo lee variables de `tokens.css` | Importar después de `tokens.css` |
| `design/reference/components.d.ts` | Props de cada componente | Contrato para reimplementarlos en TypeScript |
| `design/reference/components.reference.js` | Implementación de referencia (React 18, sin build) usada en el sistema publicado | Solo consulta: no importar en producción |
| `design/fonts/` | Barlow 400/500/600 y Barlow Condensed 500/600 (SIL OFL 1.1, licencia en `OFL.txt`) | `tokens.css` ya trae los `@font-face` con rutas `fonts/…` |

## Reglas no negociables

- Toda variable visual sale de un token por nombre (`var(--accent)`); nunca escribas un hex, rgba, px de radio o sombra suelto en el CSS de una pantalla.
- Máximo dos capas de vidrio: la ventana (`Shell`) y el tile interior (`glass-inset`). Nunca texto directo sobre el fondo (`backdrop`).
- Amarillo `accent` solo para la acción principal de la vista (en listados, una por fila), lo que el usuario eligió (silla, vuelo) y la placa AVIANCO. La opción activa del nav o de un segmentado es `invert`, no amarilla.
- Cada estado lleva palabra o ícono además del color (`Badge`).
- Toda acción irreversible (cancelar compra, cancelar vuelo, cambiar silla) pide confirmación con `Dialog` (IU-07).
- Formatos: dinero `$ 1.250.000` (IU-06), fecha `dd/mm/aaaa`, hora 24 h en la hora local de la ciudad con su zona cuando importa (IU-05), código de vuelo `STA-00021`, silla `12C`.
- Responsive a 360, 768 y 1280 px sin scroll horizontal (IU-01).
- Tema por atributo: `<html data-theme="noche">` (principal) o `data-theme="dia"`.

## Guía de marca

AVIANCO es la aerolínea (ficticia) que opera el Sistema de Tiquetes Aéreos (STA). Su interfaz toma la **señalética de un aeropuerto** y la pone **detrás de un vidrio**: paneles translúcidos y difuminados que flotan sobre la luz de un terminal, como una ventana de la app suspendida sobre la pista. Los vuelos y tiquetes se ven como pasabordos con talón, los listados como tablero de salidas y la navegación como un letrero. El amarillo de señalética es escaso a propósito: marca la acción principal o lo que el usuario eligió.

### Contenido y voz

- Español de Colombia en toda la interfaz, los correos, los PDF y el chatbot (IU-08). Trato de **tú**: «Elige tu silla», «Te queda 1 cambio».
- Botones con verbo primero y sin punto: «Agregar», «Cambiar a 9A», «Cancelar vuelo». Títulos de pantalla como frase: «24 vuelos desde Pereira».
- Las confirmaciones son preguntas con el objeto exacto: «¿Cancelar el vuelo STA-00051?», y dicen qué pasa después («Se anularán, sus sillas se liberarán y avisaremos a los clientes por correo.»).
- Los errores dicen qué está mal y cómo corregirlo, junto al campo (IU-07): «Debe ser mayor que el mínimo.»
- Sin emojis, sin signos de exclamación, sin superlativos.

#### Formatos fijos

| Dato | Formato | Ejemplo |
|---|---|---|
| Dinero (IU-06) | `$` + espacio + punto de miles, sin decimales; con `STA.cop()` | $ 1.250.000 · + $ 500.000 · − $ 800.000 |
| Fecha | dd/mm/aaaa | 10/12/2026 |
| Hora (IU-05) | 24 h, hora local de la ciudad, con su zona cuando importa | 15:00 Madrid (UTC+2) |
| Código de vuelo | `STA-` + 5 dígitos, estilo `code` | STA-00021 |
| Silla | fila + letra (Apéndice A) | 12C |
| Rótulos sobre cifras | MAYÚSCULAS, estilo `overline` | SALDO DISPONIBLE |

### Fundamentos visuales

#### Vidrio: tres capas, nunca más

1. **Backdrop** (`backdrop`, `backdrop-glow-warm`, `backdrop-glow-cool`): el fondo con luz cálida de atardecer, luz fría de ventanal y parales tenues. Va una vez, en la raíz. Si el equipo tiene una foto real del terminal, pásela a `Backdrop image=…`; `scrim` la oscurece. Nunca hay texto directo sobre el backdrop.
2. **Vidrio** (`glass` + `blur-md`, o `glass-strong` + `blur-lg` para lo que flota: nav, diálogos, chatbot). Siempre con `backdrop-filter: blur(…) saturate(140%)`, borde de 1 px `glass-edge` y `shadow-glass`.
3. **Tile** (`glass-inset`): lo que vive dentro de un panel: KPI, tarjetas de vuelo dentro de la ventana, filas destacadas.

Dentro de `Shell` (la ventana) los paneles ya son tiles: no se apila vidrio sobre vidrio. Con «reducir transparencia» o sin `backdrop-filter`, todo cae a `glass-strong` opaco.

#### Color

- Dos temas: **Noche** (el principal, vidrio oscuro como la referencia) y **Día** (vidrio escarchado claro). Cambie de tema con `data-theme="noche|dia"` en `<html>`.
- Texto: `ink` principal, `ink-muted` secundario; `ink-faint` solo para íconos decorativos y deshabilitados. Sobre vidrio, en ambos temas, `ink` y `ink-muted` superan 4,5:1 incluso con la luz del backdrop más brillante debajo (medido sobre `glass + glass-inset`).
- **Amarillo** `accent` solo para: el botón primario (uno por vista; en listados, el de cada fila), la silla elegida, el vuelo elegido y la placa «AVIANCO». Texto sobre amarillo: `on-accent`. Amarillo como texto: `accent-text` (en Día se oscurece a ocre para leerse).
- La opción activa (nav, segmentado, página actual) es una píldora `invert` / `on-invert`, no amarilla.
- Estados con palabra o ícono, nunca solo color: `success` (recarga, reembolso, en tu carrito), `info` (reserva pendiente), `danger` (agotado, error, cancelar). Sus fondos teñidos son `*-soft`.
- En Día, el relleno amarillo apenas se distingue del vidrio blanco (1,3:1): por eso la silla elegida lleva anillo interior `on-accent` y el vuelo elegido lleva además el badge «En tu carrito».

#### Tipografía

- **Barlow Condensed** (`--font-display`) es la letra del letrero: códigos IATA (`display-lg`), cifras héroe (`display-xl`), títulos (`title-lg`, `title-md`), precios (`price`) y códigos de vuelo, reserva y silla (`code`). Siempre con cifras tabulares en tablas.
- **Barlow** (`--font-sans`) para todo lo que se lee: `body`, `body-strong`, `label`, `caption`, `overline`.
- Un `title-lg` por pantalla. El `display-xl` solo para la cifra que es el propósito de la vista (el saldo).

#### Espacio, radios y sombras

- Escala de 4 px: `space-1` 4 … `space-12` 48. Paneles con `space-5`, separación entre paneles `space-6`.
- Radios: `radius-sm` sillas y celdas, `radius-md` inputs, tiles y pasabordos, `radius-lg` paneles, `radius-xl` ventana y diálogos, `radius-pill` botones, chips, segmentados y búsqueda.
- Sombras: `shadow-glass` paneles y ventana, `shadow-float` lo que flota, `shadow-accent` solo el botón primario.

#### Estados e interacción

- Hover: `glass-hover`. Foco de teclado: anillo sólido de 2 px `focus` con 2 px de separación (amarillo en Noche, tinta en Día; ≥3:1 sobre todo vidrio).
- Deshabilitado: 45 % de opacidad (botones) o 55 % (pasabordo agotado), siempre con la razón escrita al lado.
- Movimiento: transiciones de 150 ms en color y brillo; nada de animaciones decorativas.

#### Responsive (IU-01)

360, 768 y 1280 px sin desplazamiento horizontal. Bajo 720 px la ventana `Shell` ocupa la pantalla, el nav muestra solo el avatar y las rejillas de dos columnas pasan a una. Bajo 560 px de ancho, el talón del `FlightPass` baja debajo de la ruta.

### Componentes

`Backdrop`, `Shell`, `TopNav`, `Glass`, `Button`, `Badge`, `Segmented`, `Field`, `SearchPill`, `StatTile`, `FlightPass`, `Board` (+ `Board.Flap`), `Meter`, `SeatMap` (+ `SeatMap.Legend`), `Dialog`, `ChatFab`, `Icon` y el formateador `STA.cop()`. Su implementación de referencia está en `design/reference/components.reference.js` (React 18, `window.STA`); los estilos están en `design/components.css` y leen solo variables de `design/tokens.css`.

Las cuatro **Pantallas** son ejemplos armados con esos componentes a partir de los wireframes del documento de historias de usuario: S14 Resultados de búsqueda, S22 Monedero, S26 Cambio de silla y S09 Vuelos programados del administrador.

#### Uso en el frontend (Vite + TypeScript)

- Importa `tokens.css` y después `components.css` tal cual, una sola vez, en `src/main.tsx`: `import "@design/tokens.css"; import "@design/components.css";`. `@design` es el alias de Vite hacia la carpeta `design/` del repo.
- Reimplementa cada componente en `src/components/ui/` con las mismas clases `sta-*` y las props de `design/reference/components.d.ts`. `STA.cop()` pasa a ser una función de formato del frontend.
- Si un componente necesita comportamiento accesible que shadcn/ui ya resuelve (foco atrapado del `Dialog`, teclado de un select), parte del componente de shadcn/ui y píntalo con las clases `sta-*`, no con el tema por defecto de shadcn.
- Tailwind v4 es para maquetar (flex, grid, gap; su escala de 4 px coincide con `space-*`). Sus colores, radios y sombras apuntan a los tokens con `@theme inline` (`--color-accent: var(--accent);`) y la paleta por defecto se borra con `--color-*: initial;`, así no existen clases como `bg-red-500`.

### Iconografía

- Íconos de trazo 1,75 px en caja de 24, puntas y uniones redondeadas, color `currentColor` (`Icon`). Varios trazos (avión, búsqueda, calendario…) siguen la geometría de Lucide (licencia ISC); el proyecto no tenía un set propio, así que es una sustitución, no un ícono de marca.
- Los wireframes usaban glifos dentro de cajitas en el nav; aquí se reemplazan por estos íconos de línea.
- Sin emojis. Las flechas de variación (↑ ↓) van dentro de un `Badge`.

### Marca

La marca es **AVIANCO**: el nombre en Barlow Condensed SemiBold, en mayúsculas, sobre la placa amarilla `accent` con texto `on-accent` (la esquina superior izquierda del `TopNav`). No hay logotipo: no dibuje un avión-logo ni un isotipo hasta que el equipo apruebe uno. «STA» queda como nombre del software (códigos de vuelo `STA-00021`, el espacio de nombres `window.STA`), no como marca visible.

## Referencia de tokens

### Color

| Token | Noche | Día | Uso |
|---|---|---|---|
| `backdrop` | `#14171a` | `#e7e3dc` | Fondo sólido de la página, debajo de todo el vidrio. Nunca lleva texto directo: el texto siempre va sobre un panel de vidrio. |
| `backdrop-glow-warm` | `rgba(214,146,56,0.62)` | `rgba(240,178,84,0.50)` | Luz cálida del fondo (atardecer sobre la pista). Solo en el gradiente de .sta-backdrop; le da al vidrio algo que difuminar. |
| `backdrop-glow-cool` | `rgba(72,126,132,0.55)` | `rgba(120,170,176,0.42)` | Luz fría del fondo (ventanal del terminal). Solo en el gradiente de .sta-backdrop. |
| `glass` | `rgba(34,37,42,0.70)` | `rgba(255,255,255,0.56)` | Vidrio base: paneles, tarjetas de vuelo, barra lateral de filtros. Siempre con backdrop-filter blur-md. |
| `glass-strong` | `rgba(22,24,27,0.82)` | `rgba(255,255,255,0.84)` | Vidrio denso: barra de navegación, diálogos, menús, la ventana del chatbot. Más opaco porque flota sobre contenido. |
| `glass-inset` | `rgba(255,255,255,0.06)` | `rgba(255,255,255,0.55)` | Tile dentro de un panel (KPI, fila destacada, talón del pasabordo). Se apila sobre glass, nunca va solo sobre el fondo. |
| `glass-hover` | `rgba(255,255,255,0.10)` | `rgba(255,255,255,0.75)` | Hover de filas, tarjetas y botones secundarios. |
| `glass-edge` | `rgba(255,255,255,0.12)` | `rgba(255,255,255,0.75)` | Borde de 1px de todo vidrio. Decorativo: la separación la da el blur y la sombra, no este borde. |
| `glass-highlight` | `rgba(255,255,255,0.14)` | `rgba(255,255,255,0.95)` | Reflejo interior superior (inset 0 1px 0) de paneles y botones. |
| `scrim` | `rgba(8,9,10,0.55)` | `rgba(40,36,30,0.35)` | Velo detrás de un diálogo modal. |
| `field` | `rgba(0,0,0,0.30)` | `rgba(255,255,255,0.72)` | Relleno de inputs, selects y la búsqueda, sobre glass. |
| `control-line` | `#959aa3` | `#7b8088` | Borde de inputs, selects, sillas libres y botón secundario: ≥3:1 sobre glass y field en ambos temas. |
| `ink` | `#f3f4f5` | `#15171a` | Texto principal sobre glass, glass-strong, glass-inset y field. |
| `ink-muted` | `#b3b8bf` | `#50555c` | Texto secundario: ciudades bajo el código IATA, metadatos, etiquetas de campo. Sobre glass, glass-inset y field. |
| `ink-faint` | `#999ea6` | `#6b7078` | Íconos decorativos, placeholder de búsqueda, texto deshabilitado. Solo marcas ≥3:1; no para texto de lectura. |
| `accent` | `#f5c518` | `#f5c518` | Amarillo de señalética: SOLO la acción principal de la vista o lo que el usuario eligió (su silla, su vuelo). Relleno, no texto en Día. |
| `on-accent` | `#15171a` | `#15171a` | Texto e íconos sobre un relleno accent (el label del botón primario, la silla elegida). |
| `accent-text` | `#f5c518` | `#7a5a00` | Amarillo como texto o borde (precio de promoción, enlace activo del nav) sobre glass o accent-soft. |
| `accent-soft` | `rgba(245,197,24,0.10)` | `rgba(245,197,24,0.28)` | Fondo teñido de chips de promoción y del item activo del nav, detrás de accent-text. |
| `success` | `#72e39e` | `#17683a` | Estado positivo con palabra o flecha: recarga, reembolso, 'Activa', variación ↑. Sobre glass o success-soft. |
| `success-soft` | `rgba(114,227,158,0.10)` | `rgba(23,104,58,0.10)` | Fondo de chips de éxito, detrás de success. |
| `danger` | `#ffb4a9` | `#a1221b` | Error de validación, 'Agotado', cancelar vuelo, variación ↓. Siempre con palabra o ícono. Sobre glass o danger-soft. |
| `danger-soft` | `rgba(255,165,152,0.10)` | `rgba(161,34,27,0.09)` | Fondo de chips de error y de la caja de aviso de un diálogo destructivo. |
| `info` | `#a0d3ff` | `#1f5fa8` | Estado informativo: 'Reserva' (pendiente de pago), 'Check-in abierto'. Sobre glass o info-soft. |
| `info-soft` | `rgba(160,211,255,0.10)` | `rgba(31,95,168,0.10)` | Fondo de chips informativos, detrás de info. |
| `focus` | `#f5c518` | `#15171a` | Anillo de foco de teclado: 2px sólidos con 2px de separación. ≥3:1 sobre todo vidrio. |
| `invert` | `#f3f4f5` | `#15171a` | Relleno invertido (claro en Noche, oscuro en Día): opción activa de un segmentado, burbuja del usuario en el chatbot. |
| `on-invert` | `#15171a` | `#f3f4f5` | Texto e íconos sobre invert. |
| `seat-current` | `{invert}` | `{invert}` | Relleno de 'Tu silla actual' en el mapa de sillas (alias de invert). |
| `on-seat-current` | `{on-invert}` | `{on-invert}` | Texto sobre seat-current (alias de on-invert). |
| `seat-taken` | `rgba(255,255,255,0.10)` | `rgba(21,23,26,0.10)` | Relleno de silla ocupada (con rayado en ink-faint). No seleccionable. |

### Tipografía

Familias: `--font-display` = Barlow Condensed, Arial Narrow, sans-serif · `--font-sans` = Barlow, system-ui, -apple-system, Segoe UI, sans-serif

| Clase | Familia | Tamaño / interlineado | Peso | Uso |
|---|---|---|---|---|
| `.display-xl` | display | 52px / 56px | 600 | Cifras héroe: saldo del monedero, total a pagar. |
| `.display-lg` | display | 36px / 40px | 600 | Códigos IATA en el pasabordo y horas grandes. |
| `.title-lg` | display | 30px / 36px | 600 | Título de pantalla, uno por vista. |
| `.title-md` | display | 20px / 26px | 600 | Título de panel o diálogo. |
| `.price` | display | 24px / 28px | 600 | Precio en la tarjeta de vuelo y en el carrito. |
| `.code` | display | 15px / 20px | 600 | Código de vuelo, código de reserva, silla (12C) y horas del tablero. |
| `.body` | sans | 15px / 22px | 400 | Texto corrido y celdas de tabla. |
| `.body-strong` | sans | 15px / 22px | 600 | Énfasis dentro de body, nombres. |
| `.label` | sans | 13px / 18px | 500 | Etiquetas de campo, items del nav, botones. |
| `.caption` | sans | 12px / 16px | 500 | Ciudad bajo el IATA, zona horaria, ayudas de campo. |
| `.overline` | sans | 11px / 14px | 600 | Rótulo sobre una cifra o un grupo; se escribe en mayúsculas en el texto. |

### Espaciado

| Token | Valor | Uso |
|---|---|---|
| `--space-1` | `4px` | Separación ícono–texto. |
| `--space-2` | `8px` | Gap entre chips; padding vertical de chips. |
| `--space-3` | `12px` | Gap entre campos; padding de filas de tabla. |
| `--space-4` | `16px` | Padding de tiles y del talón del pasabordo. |
| `--space-5` | `20px` | Padding de paneles. |
| `--space-6` | `24px` | Gap entre paneles; margen interior de la ventana. |
| `--space-8` | `32px` | Separación entre secciones de una pantalla. |
| `--space-12` | `48px` | Margen de la ventana sobre el fondo en escritorio. |

### Radios

| Token | Valor | Uso |
|---|---|---|
| `--radius-sm` | `8px` | Sillas, checkboxes, celdas del tablero. |
| `--radius-md` | `14px` | Inputs, tiles internos, tarjetas de vuelo. |
| `--radius-lg` | `20px` | Paneles de vidrio. |
| `--radius-xl` | `28px` | La ventana principal de la app y los diálogos. |
| `--radius-pill` | `999px` | Botones, chips, segmentados, búsqueda, FAB del chatbot. |

### Blur (backdrop-filter)

| Token | Valor | Uso |
|---|---|---|
| `--blur-sm` | `12px` | Chips y botones secundarios sobre imágenes. |
| `--blur-md` | `24px` | Paneles y tarjetas (glass). |
| `--blur-lg` | `40px` | Barra de navegación, diálogos y ventana del chatbot (glass-strong). |

### Sombras

| Token | Noche | Día | Uso |
|---|---|---|---|
| `--shadow-glass` | `0 18px 48px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.10)` | `0 18px 44px rgba(60,48,30,0.16), inset 0 1px 0 rgba(255,255,255,0.90)` | Paneles y la ventana principal. |
| `--shadow-float` | `0 24px 64px rgba(0,0,0,0.60), inset 0 1px 0 rgba(255,255,255,0.12)` | `0 24px 60px rgba(60,48,30,0.24), inset 0 1px 0 rgba(255,255,255,0.95)` | Diálogos, menús y el FAB del chatbot. |
| `--shadow-accent` | `0 6px 20px rgba(245,197,24,0.28)` | `0 6px 18px rgba(180,130,0,0.28)` | Halo del botón primario. |

## Componentes

Cada componente usa las clases `sta-*` de `design/components.css`. Las props completas están en `design/reference/components.d.ts`.

### Backdrop

El suelo de la app: un fondo con luz cálida (`backdrop-glow-warm`), luz fría (`backdrop-glow-cool`) y los parales tenues de un ventanal de terminal, para que el vidrio tenga algo que difuminar.

- Va UNA vez, en la raíz de la página (`<Backdrop>` o la clase `.sta-backdrop` en el `<body>`/contenedor raíz).
- `image`: URL de una foto real (terminal, pista al atardecer). Se oscurece sola con `scrim`. Úsela si el equipo tiene fotos propias; sin foto, el gradiente basta.
- Nunca ponga texto directamente sobre el Backdrop: siempre sobre `Glass`.

### Shell

La ventana principal de la app flotando sobre el Backdrop, como en la referencia: `glass` con `radius-xl`, la `TopNav` arriba, el contenido y el botón «Información» del chatbot.

- Props: `nav` (un `TopNav`), `children` (la pantalla), `chat={false}` para ocultar el FAB (administrador y root no usan chatbot, Apéndice B).
- Dentro del Shell, los `Glass` y `FlightPass` se pintan como tiles `glass-inset` (no se apila vidrio sobre vidrio). Así el contraste medido es `glass + glass-inset`.
- Bajo 720 px el Shell pierde margen y esquinas y ocupa la pantalla (IU-01).

### TopNav

La barra «letrero» (IU-02): placa amarilla con el nombre de la aerolínea, «AVIANCO», items del rol y, a la derecha, búsqueda, carrito y usuario.

- `items`: `[{label, icon, href, active}]`. Cliente: Vuelos, Noticias, Mis viajes, Monedero, Muro. Administrador: Vuelos programados, Promociones, Vuelos realizados, Muros, Auditoría. Visitante: Vuelos, Noticias, Check-in + botones Iniciar sesión / Crear cuenta en `right`.
- El item activo es una píldora `invert` (como el filtro activo de la referencia), NO amarilla: el amarillo queda para la acción principal.
- `user`: `{name, role}`; las iniciales salen solas.
- `brand`: texto de la placa; por defecto «AVIANCO».

### Glass

El panel de vidrio: `glass` + `blur-md` + `radius-lg` + `shadow-glass`, con borde `glass-edge`.

- `variant`: `base` (paneles, filtros), `strong` (flota sobre contenido: menús, chatbot), `inset` (tile dentro de un panel: KPI, fila destacada).
- `title` y `actions` arman el encabezado del panel (`title-md` a la izquierda, acciones a la derecha).
- Sin soporte de `backdrop-filter` (o con «reducir transparencia») cae a `glass-strong` opaco: el texto sigue legible.
- No: vidrio sobre vidrio sobre vidrio. Máximo dos capas (ventana + tile).

### Button

Píldora de 40 px (`sm`: 32 px). **Primary** (amarillo `accent`, texto `on-accent`) solo para la acción por la que existe la vista: Agregar, Pagar, Programar vuelo, Cambiar a 9A.

- `variant`: `primary` · `secondary` (vidrio con borde `control-line`, la opción por defecto) · `ghost` (acciones de barra: Carrito, Eliminar) · `danger` (borde y texto `danger`: Cancelar vuelo, Fuerza mayor).
- `icon`, `iconAfter`: nombre de `Icon`. `block`: ancho completo. `disabled`: queda al 45 %.
- Verbo primero, sin punto: «Agregar», «Cancelar vuelo», «Confirmar 12C».
- Toda acción irreversible abre un `Dialog` de confirmación (IU-07).

### Badge

Una o pocas palabras de estado en píldora de 24 px, siempre con palabra (y si ayuda, ícono): el color nunca va solo.

- `tone`: `neutral` (Sin ventas, Compra) · `accent` (Promoción −20 %) · `success` (En tu carrito, Reembolso, ↑) · `info` (Reserva · vence…, 2 reservas activas) · `danger` (Agotado, ↓).
- `icon` opcional: `tag`, `check`, `x`, `arrow-up`, `arrow-down`.

### Segmented

Filtro de pocas opciones excluyentes en una píldora (`field`); la activa se pinta `invert`.

- `options`: `['Todos','Recargas',…]` o `[{value,label}]`; `value`/`onChange` para controlarlo, o `defaultValue`.
- `label`: nombre accesible del grupo. Máximo 5 opciones; más, use un `Field` select.

### Field

Etiqueta + control + mensaje. Input o select (`options`) de 40 px, `radius-md`, fondo `field`, borde `control-line`.

- Props: `label`, `value`, `placeholder`, `hint`, `error`, `icon`, `options`, `type`.
- `error` pinta el borde `danger` y muestra junto al campo qué está mal y cómo corregirlo, en español (IU-07): «Debe ser mayor que el mínimo.»
- Fechas `dd/mm/aaaa`, horas 24 h, dinero `$ 1.250.000` (IU-05, IU-06).

### SearchPill

Búsqueda en píldora para la barra o la parte alta de una vista, como «Barcelona, Spain» en la referencia.

- Props: `placeholder`, `value`, `label`, `onFilters` (abre filtros; `false` lo oculta).
- Es un acceso rápido; la búsqueda completa de vuelos vive en el panel de Filtros.

### StatTile

Una cifra con su rótulo, en tile `glass-inset`: saldo del monedero, totales, métricas del administrador.

- Props: `label` (se muestra en `overline`), `value` (ya formateado: use `STA.cop()`), `delta` `{dir:'up'|'down', text, tone}`, `foot`, `action`, `hero` (cifra a 52 px, una por vista).
- Solo cifras reales del sistema; nada de métricas de relleno.

### FlightPass

El vuelo como pasabordo con talón: ruta grande a la izquierda y, tras la línea punteada con muescas, el código, el precio y la acción.

- Props: `from`/`to` `{iata, city, time, tz}`, `duration`, `code`, `price`, `oldPrice` (activa el estilo de promoción), `priceNote`, `badges` `[{tone, icon, label}]`, `note`, `date`, `action` (un `Button`), `state` `default|selected|soldout`.
- `selected`: borde `accent` + badge «En tu carrito» (el borde solo no basta en Día). `soldout`: 55 % + badge `danger`.
- Horas en hora local de cada ciudad (IU-05); si la ciudad cambia de zona, pase `tz` («UTC+1»).
- Bajo 560 px de ancho el talón baja debajo de la ruta.

### Board

Tablero de salidas para listados: vuelos programados, vuelos realizados, movimientos, auditoría.

- Props: `columns` `[{key, label, align:'right', render(row)}]`, `rows`, `highlight` (índice de fila resaltada), `caption` (accesible).
- `Board.Flap` pinta la fecha/hora como una paleta del tablero; úsela en la primera columna.
- Cifras alineadas a la derecha con `align:'right'`. Movimientos: `STA.cop(v, {sign:true})` → «+ $ 500.000» / «− $ 800.000».

### Meter

Ocupación de un vuelo: barra de 84 px + «143/250».

- Props: `value`, `max` (150 nacional, 250 internacional). Uso: columna Ocupación de los vuelos programados.

### SeatMap

El mapa de la cabina vista desde arriba (IU-04), con la distribución nacional del Apéndice A: filas 1–5 primera y 6–30 económica, letras AB | CDE.

- Props: `current` («12C»), `selected`, `onSelect(code)`, `taken` (lista de códigos), `ticketClass` (`economica` atenúa y bloquea primera; `primera`, al revés), `fromRow`/`toRow`, `maxHeight` (desplazamiento), `footer`.
- Estados: libre (borde `control-line`), ocupada (rayada, no seleccionable), tu silla actual (`seat-current`), la que eliges (`accent` con anillo interior `on-accent`).
- `SeatMap.Legend` muestra las cuatro convenciones; póngala al lado del mapa.
- Pendiente: la cabina internacional (2-1-2 y 3-4-3, letras sin I) no está construida aún.

### Dialog

Confirmación de acciones irreversibles (IU-07): cancelar compra, cancelar vuelo, cambiar silla.

- Props: `title` (pregunta: «¿Cancelar el vuelo STA-00051?»), `subtitle` (ruta y fecha), `notice` + `tone` (`danger`|`info`: qué pasa después), `children` (detalle), `actions`, `inline` (sin velo, para incrustar).
- Acción destructiva en `danger` primero, «Volver» como `secondary`.
- El velo (`scrim`) cubre solo el contenedor más cercano con `position: relative` (el Shell).

### ChatFab

El botón flotante «Información» que abre el chatbot (IU-03), abajo a la derecha en todas las páginas de visitante y cliente.

- Props: `onClick`, `label`, `static` (en flujo, para documentación).
- Disco `accent` con el ícono `info` sobre píldora `glass-strong`. No lo muestre a administradores ni root.

### Icon

Íconos de trazo 1,75 px en caja de 24, que heredan `currentColor`.

- Props: `name`, `size` (`sm` 14 · por defecto 18 · `lg` 22), `label` (si el ícono va solo y significa algo).
- Nombres: `STA.Icon.names`.

## Pantallas de referencia

Ejemplos armados con estos componentes a partir de los wireframes de las historias de usuario (se ven en el sistema publicado y en el PDF `AVIANCO_Sistema_de_diseno.pdf`):

- **PantallaResultados**: Ejemplo: S14 Resultados de búsqueda (HU-20) en estilo vidrio: filtros con un error de validación a la izquierda y tres pasabordos (promoción, en el carrito, agotado).
- **PantallaMonedero**: Ejemplo: S22 Monedero (HU-29, HU-31): saldo héroe, tarjetas simuladas, totales y el tablero de movimientos. Los totales y saldos cuadran con los movimientos (saldo inicial $ 0, SUP-39).
- **PantallaSillas**: Ejemplo: S26 Cambio o confirmación de silla (HU-39): 12C actual, 9A elegida, primera clase atenuada para un tiquete de económica.
- **PantallaVuelosAdmin**: Ejemplo: S09 Vuelos programados del administrador (HU-15, HU-16) con el diálogo de cancelación de un vuelo con reservas activas.

## Checklist antes de dar por terminada una pantalla

- [ ] ¿Usa solo tokens y clases `sta-*`?
- [ ] ¿Hay como mucho un botón `primary` por vista (o uno por fila en un listado)?
- [ ] ¿Se ve bien en Noche y en Día?
- [ ] ¿Funciona a 360 px sin scroll horizontal?
- [ ] ¿Los errores aparecen junto al campo, en español, diciendo cómo corregirlos?
- [ ] ¿Dinero, fechas y horas siguen los formatos de IU-05 e IU-06?
- [ ] ¿Las acciones irreversibles piden confirmación?
