// Todos los handlers de la API simulada. Los usan el navegador (browser.ts) y los tests.
import { noticiasHandlers } from "./handlers/noticias";
import { usuariosHandlers } from "./handlers/usuarios";
import { vuelosHandlers } from "./handlers/vuelos";

export const handlers = [...usuariosHandlers, ...vuelosHandlers, ...noticiasHandlers];
