import { getResponse } from "msw";
import { handlers } from "./handlers";
import { CONTRASENA_MOCK } from "./datos";

/** Resuelve la petición con los handlers de MSW, sin red ni service worker. */
async function api(metodo: string, ruta: string, cuerpo?: unknown) {
  const request = new Request(new URL(ruta, window.location.origin), {
    method: metodo,
    headers: cuerpo === undefined ? {} : { "Content-Type": "application/json" },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
  const respuesta = await getResponse(handlers, request);
  if (!respuesta) throw new Error(`Sin handler: ${metodo} ${ruta}`);
  const texto = await respuesta.text();
  return { status: respuesta.status, body: texto ? JSON.parse(texto) : undefined };
}

const entrar = (usuario: string) =>
  api("POST", "/api/v1/auth/login", { usuario, contrasena: CONTRASENA_MOCK });

const bogotaMadrid = (fecha_salida: string) => ({
  origen: "BOG",
  destino: "MAD",
  fecha_salida,
  hora_salida: "22:00",
  duracion_minutos: 600,
  precio_economica: 2_450_000,
  precio_primera: 6_900_000,
});

beforeEach(() => sessionStorage.clear());

describe("API simulada (MSW)", () => {
  it("inicia sesión con los usuarios de prueba y rechaza la contraseña errada (HU-03)", async () => {
    expect((await entrar("cruiz")).body).toMatchObject({ rol: "admin", registro_completo: true });
    expect((await api("GET", "/api/v1/auth/me")).body.nombre_usuario).toBe("cruiz");

    const errada = await api("POST", "/api/v1/auth/login", { usuario: "cruiz", contrasena: "x" });
    expect(errada.body.error.codigo).toBe("credenciales_invalidas");
    expect((await entrar("bloqueado")).status).toBe(429);
  });

  it("aplica los roles como el backend (RNF-10) y bloquea al administrador sin registro (HU-12)", async () => {
    expect((await api("GET", "/api/v1/vuelos")).status).toBe(401);
    await entrar("lauragomez");
    expect((await api("GET", "/api/v1/vuelos")).status).toBe(403);
    await entrar("jtorres");
    expect((await api("GET", "/api/v1/vuelos")).body.error.codigo).toBe("registro_incompleto");
  });

  it("calcula la llegada en UTC con el horario de verano del destino (RF-15)", async () => {
    await entrar("cruiz");
    // 22:00 en Bogotá (UTC-5) + 10 h = 15:00 en Madrid (UTC+2) en verano.
    const verano = await api("POST", "/api/v1/vuelos/vista-previa", bogotaMadrid("2027-07-10"));
    expect(verano.body).toMatchObject({
      tipo: "internacional",
      salida: "2027-07-11T03:00:00Z",
      llegada: "2027-07-11T13:00:00Z",
      capacidad: { primera: 50, economica: 200, total: 250 },
    });
  });

  it("simula los errores de programar un vuelo (HU-13)", async () => {
    await entrar("cruiz");
    const ruta = await api("POST", "/api/v1/vuelos", {
      ...bogotaMadrid("2027-01-10"),
      origen: "MZL",
      destino: "MIA",
    });
    expect(ruta.body.error.codigo).toBe("ruta_no_permitida");
    // STA-00088 ya sale de Bogotá a Madrid el 10/12/2026 a las 22:00 (RF-16).
    const duplicado = await api("POST", "/api/v1/vuelos", bogotaMadrid("2026-12-10"));
    expect(duplicado.status).toBe(409);
    expect(duplicado.body.error.codigo).toBe("vuelo_duplicado");
  });

  it("bloquea editar o cancelar un vuelo con ventas (HU-15, HU-16)", async () => {
    await entrar("cruiz");
    const edicion = await api("PUT", "/api/v1/vuelos/51", bogotaMadrid("2027-01-10"));
    expect(edicion.body.error.codigo).toBe("vuelo_con_reservas");
    expect((await api("POST", "/api/v1/vuelos/88/cancelar")).body.error.codigo).toBe(
      "vuelo_con_tiquetes",
    );

    const cancelado = await api("POST", "/api/v1/vuelos/51/cancelar");
    expect(cancelado.body).toMatchObject({ reservas_anuladas: 2, vuelo: { estado: "cancelado" } });
  });

  it("no acumula promociones en la misma clase (HU-17)", async () => {
    await entrar("cruiz");
    const promocion = {
      porcentaje: 30,
      clases: ["primera"],
      inicio: "2026-11-20T10:00:00-05:00",
      fin: "2026-11-22T10:00:00-05:00",
    };
    expect((await api("POST", "/api/v1/vuelos/88/promociones", promocion)).body.error.codigo).toBe(
      "promocion_duplicada",
    );
  });

  it("arma el carrusel con promociones vigentes primero y como máximo 10 elementos (HU-19)", async () => {
    const { body: carrusel } = await api("GET", "/api/v1/noticias/carrusel");
    expect(carrusel.length).toBeLessThanOrEqual(10);
    expect(carrusel[0]).toMatchObject({ tipo: "promocion", vigente: true });
    expect(carrusel.every((n: { vigente: boolean }) => n.vigente)).toBe(true);
  });
});
