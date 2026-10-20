// Cliente tipado de la API. Los tipos salen de schema.d.ts, que genera `npm run gen:api`
// desde /openapi.json del backend: nunca se escriben a mano.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type ErrorDetalle = Schemas["ErrorDetalle"];

/** Error de la API con el formato único: `codigo` estable para decidir, `mensaje` para mostrar. */
export class ApiError extends Error {
  readonly status: number;
  readonly codigo: string;
  readonly campos: Record<string, string>;

  constructor(status: number, detalle: Partial<ErrorDetalle> | undefined) {
    super(detalle?.mensaje ?? "No pudimos comunicarnos con el servidor. Intenta de nuevo.");
    this.name = "ApiError";
    this.status = status;
    this.codigo = detalle?.codigo ?? "error_desconocido";
    this.campos = detalle?.campos ?? {};
  }
}

// Mismo origen: Vite reenvía /api al backend y la cookie httpOnly viaja sola. La URL base es
// absoluta porque fetch fuera del navegador (tests) no acepta rutas relativas.
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: "same-origin",
});

type Resultado<T> = { data?: T; error?: unknown; response: Response };

/** Devuelve `data` o lanza ApiError con el cuerpo `{"error": {...}}` de la respuesta. */
export async function unwrap<T>(peticion: Promise<Resultado<T>>): Promise<T> {
  const { data, error, response } = await peticion;
  if (!response.ok) {
    const detalle = (error as { error?: Partial<ErrorDetalle> } | undefined)?.error;
    throw new ApiError(response.status, detalle);
  }
  return data as T;
}
