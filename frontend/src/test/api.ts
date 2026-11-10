import { DEPARTAMENTOS, PAISES, municipiosDe } from "@/mocks/lugares";

type Respuesta = { status: number; body?: unknown };
/** Una respuesta fija, o una función de la URL pedida (para listados con parámetros). */
type Rutas = Record<string, Respuesta | ((url: URL) => Respuesta)>;

/** El catálogo de lugares lo piden los formularios de registro y perfil: va siempre, salvo que
 *  el test lo reemplace. */
const CATALOGO: Rutas = {
  "GET /api/v1/lugares/paises": { status: 200, body: PAISES },
  "GET /api/v1/lugares/departamentos": { status: 200, body: DEPARTAMENTOS },
  ...Object.fromEntries(
    DEPARTAMENTOS.map((departamento) => [
      `GET /api/v1/lugares/departamentos/${departamento.codigo}/municipios`,
      { status: 200, body: municipiosDe(departamento.codigo) },
    ]),
  ),
};

/** Simula la API: las llaves son "MÉTODO /ruta", p. ej. "POST /api/v1/auth/login". */
export function responderApi(rutas: Rutas) {
  const respuestas = { ...CATALOGO, ...rutas };
  vi.mocked(fetch).mockImplementation(async (input) => {
    const req = input as Request;
    const llave = `${req.method} ${new URL(req.url).pathname}`;
    const entrada = respuestas[llave];
    if (!entrada) throw new Error(`Petición no simulada: ${llave}`);
    const r = typeof entrada === "function" ? entrada(new URL(req.url)) : entrada;
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
