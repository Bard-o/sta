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
    // 22:00 en Bogotá (UTC-5) + 10 h 35 min = 15:35 en Madrid (UTC+2) en verano.
    const verano = await api("POST", "/api/v1/vuelos/vista-previa", bogotaMadrid("2027-07-10"));
    expect(verano.body).toMatchObject({
      tipo: "internacional",
      salida: "2027-07-11T03:00:00Z",
      llegada: "2027-07-11T13:35:00Z",
      duracion_minutos: 635,
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

  it("rechaza en el registro una contraseña con espacios y nombres inválidos (HU-01, RNF-08, RF-03)", async () => {
    const cliente = {
      tipo_documento: "CC",
      numero_documento: "1088000111",
      nombres: "María José",
      apellidos: "O'Neill",
      fecha_nacimiento: "1999-05-10",
      lugar_nacimiento: "Pereira",
      direccion_facturacion: "Calle 1 # 2-3",
      genero: "femenino",
      email: "maria.jose@correo.co",
      telefono: "3101234567",
      nombre_usuario: "mariajose",
      contrasena: "Clave1234",
      acepta_politica: true,
    };
    const conEspacio = await api("POST", "/api/v1/usuarios/registro", {
      ...cliente,
      contrasena: "Clave 1234",
    });
    expect(conEspacio.status).toBe(422);
    expect(conEspacio.body.error.codigo).toBe("datos_invalidos");
    expect(conEspacio.body.error.campos.contrasena).toBe(
      "Mínimo 8 caracteres, con al menos una letra y un número, sin espacios.",
    );

    const nombres = await api("POST", "/api/v1/usuarios/registro", {
      ...cliente,
      nombres: "1234",
      apellidos: "Gómez#",
    });
    expect(nombres.status).toBe(422);
    expect(nombres.body.error.campos).toMatchObject({
      nombres: "El formato no es válido.",
      apellidos: "El formato no es válido.",
    });

    expect((await api("POST", "/api/v1/usuarios/registro", cliente)).status).toBe(201);
  });

  it("valida el formato de los datos del perfil como el backend (HU-07, RF-03)", async () => {
    await entrar("lauragomez");
    const { body: perfil } = await api("GET", "/api/v1/usuarios/me/perfil");
    const edicion = { ...perfil, telefono: "3101234567" };

    const nombres = await api("PUT", "/api/v1/usuarios/me/perfil", { ...edicion, nombres: "1234" });
    expect(nombres.status).toBe(422);
    expect(nombres.body.error.codigo).toBe("datos_invalidos");
    expect(nombres.body.error.campos.nombres).toBe("El formato no es válido.");

    // Seis dígitos no alcanzan el mínimo de siete del teléfono.
    const telefono = await api("PUT", "/api/v1/usuarios/me/perfil", {
      ...edicion,
      telefono: "123456",
    });
    expect(telefono.status).toBe(422);
    expect(telefono.body.error.campos.telefono).toBe("El formato no es válido.");

    const largo = await api("PUT", "/api/v1/usuarios/me/perfil", {
      ...edicion,
      lugar_nacimiento: "x".repeat(121),
    });
    expect(largo.body.error.campos.lugar_nacimiento).toBe("Es demasiado largo.");

    expect((await api("PUT", "/api/v1/usuarios/me/perfil", edicion)).status).toBe(200);
  });

  it("valida los datos personales del registro del administrador antes de sus reglas de negocio (HU-12, RF-03)", async () => {
    await entrar("jtorres");
    const registro = {
      tipo_documento: "CC",
      numero_documento: "1088000222",
      nombres: "Juan",
      apellidos: "Torres",
      fecha_nacimiento: "1990-03-02",
      lugar_nacimiento: "Cali",
      direccion_facturacion: "Carrera 5 # 6-7",
      genero: "masculino",
      email: "jtorres@avianca.test",
      contrasena_temporal: CONTRASENA_MOCK,
      contrasena_nueva: "Nueva1234",
      confirmacion: "Nueva1234",
    };
    const invalido = await api("POST", "/api/v1/administradores/me/registro", {
      ...registro,
      nombres: "1234",
      contrasena_temporal: "otra",
    });
    expect(invalido.status).toBe(422);
    expect(invalido.body.error.codigo).toBe("datos_invalidos");
    expect(invalido.body.error.campos.nombres).toBe("El formato no es válido.");

    const espacios = await api("POST", "/api/v1/administradores/me/registro", {
      ...registro,
      contrasena_nueva: "Nueva 1234",
      confirmacion: "Nueva 1234",
    });
    expect(espacios.body.error.campos.contrasena_nueva).toBe(
      "Mínimo 8 caracteres, con al menos una letra y un número, sin espacios.",
    );

    expect((await api("POST", "/api/v1/administradores/me/registro", registro)).status).toBe(200);
  });
});
