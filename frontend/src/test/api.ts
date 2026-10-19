type Respuesta = { status: number; body?: unknown };
type Rutas = Record<string, Respuesta>;

/** Simula la API: las llaves son "MÉTODO /ruta", p. ej. "POST /api/v1/auth/login". */
export function responderApi(rutas: Rutas) {
  vi.mocked(fetch).mockImplementation(async (input) => {
    const req = input as Request;
    const llave = `${req.method} ${new URL(req.url).pathname}`;
    const r = rutas[llave];
    if (!r) throw new Error(`Petición no simulada: ${llave}`);
    return new Response(r.body === undefined ? null : JSON.stringify(r.body), {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

export const SIN_SESION: Respuesta = {
  status: 401,
  body: { error: { codigo: "no_autenticado", mensaje: "Inicia sesión para continuar." } },
};

export const ROOT = {
  id: 1,
  nombre_usuario: "root",
  email: null,
  rol: "root",
  email_verificado: false,
} as const;
