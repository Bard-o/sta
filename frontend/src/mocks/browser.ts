// API simulada en el navegador. Se activa con VITE_API_MOCK=true (ver src/main.tsx) para
// avanzar en las pantallas mientras el backend responde 501 (docs/api/iteracion-1.md).
import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);
