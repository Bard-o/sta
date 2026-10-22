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

type Usuario = import("@/api/client").Schemas["UsuarioSalida"];

export const ROOT: Usuario = {
  id: 1,
  nombre_usuario: "root",
  email: null,
  rol: "root",
  email_verificado: false,
  registro_completo: true,
  nombres: null,
  apellidos: null,
};

export const CLIENTE: Usuario = {
  id: 12,
  nombre_usuario: "lauragomez",
  email: "laura.gomez@correo.co",
  rol: "cliente",
  email_verificado: true,
  registro_completo: true,
  nombres: "Laura",
  apellidos: "Gómez Ríos",
};

export const ADMIN: Usuario = {
  id: 3,
  nombre_usuario: "cruiz",
  email: "carlos.ruiz@avianco.test",
  rol: "admin",
  email_verificado: true,
  registro_completo: true,
  nombres: "Carlos",
  apellidos: "Ruiz",
};

/** Administrador que aún no completó su registro (HU-12). */
export const ADMIN_INCOMPLETO: Usuario = {
  id: 5,
  nombre_usuario: "jtorres",
  email: null,
  rol: "admin",
  email_verificado: false,
  registro_completo: false,
  nombres: null,
  apellidos: null,
};

export const sesionDe = (usuario: Usuario): Respuesta => ({ status: 200, body: usuario });
