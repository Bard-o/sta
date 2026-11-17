// Todos los handlers de la API simulada. Los usan el navegador (browser.ts) y los tests.
import { busquedaHandlers } from "./handlers/busqueda";
import { carritoHandlers } from "./handlers/carrito";
import { lugaresHandlers } from "./handlers/lugares";
import { monederoHandlers } from "./handlers/monedero";
import { noticiasHandlers } from "./handlers/noticias";
import { reservasHandlers } from "./handlers/reservas";
import { usuariosHandlers } from "./handlers/usuarios";
import { vuelosHandlers } from "./handlers/vuelos";

export const handlers = [
  ...usuariosHandlers,
  ...vuelosHandlers,
  ...noticiasHandlers,
  ...lugaresHandlers,
  ...busquedaHandlers,
  ...carritoHandlers,
  ...reservasHandlers,
  ...monederoHandlers,
];
