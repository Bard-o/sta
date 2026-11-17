import { getResponse } from "msw";
import { handlers } from "./handlers";
import { CONTRASENA_MOCK } from "./datos";
import { db } from "./estado";

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

/** El root invita a un administrador y devuelve el token de su correo. */
async function invitar(nombre: string) {
  await entrar("root");
  const alta = await api("POST", "/api/v1/administradores", {
    nombre_usuario: nombre,
    email: `${nombre}@avianco.test`,
  });
  const invitacion = db.invitaciones.find((i) => i.admin_id === alta.body.id && !i.usado);
  if (!invitacion) throw new Error("La invitación no quedó guardada.");
  return { admin: alta.body, token: invitacion.token };
}

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

  it("aplica los roles como el backend y un administrador invitado no puede entrar (RNF-10, HU-12)", async () => {
    expect((await api("GET", "/api/v1/vuelos")).status).toBe(401);
    await entrar("lauragomez");
    expect((await api("GET", "/api/v1/vuelos")).status).toBe(403);
    // jtorres está invitado: todavía no tiene contraseña.
    expect((await entrar("jtorres")).status).toBe(401);
    await api("POST", "/api/v1/auth/logout");
    expect((await api("GET", "/api/v1/vuelos")).status).toBe(401);
  });

  it("invita, valida y completa el registro desde el enlace (HU-10, HU-12)", async () => {
    const { admin, token } = await invitar("nuevoadmin");
    expect(admin.estado).toBe("invitacion_pendiente");

    const validacion = await api("POST", "/api/v1/administradores/invitacion/validar", { token });
    expect(validacion.status).toBe(200);
    expect(validacion.body).toMatchObject({
      nombre_usuario: "nuevoadmin",
      email: "nuevoadmin@avianco.test",
    });

    const completa = await api("POST", "/api/v1/administradores/invitacion/completar", {
      token,
      tipo_documento: "CC",
      numero_documento: "1088000111",
      nombres: "Nuevo",
      apellidos: "Administrador",
      fecha_nacimiento: "1992-04-12",
      lugar_nacimiento: { pais: "CO", municipio: "11001", ciudad: null },
      direccion_facturacion: "Calle 10 # 20-30",
      genero: "masculino",
      contrasena: "Nueva1234",
      confirmacion: "Nueva1234",
    });
    expect(completa.status).toBe(200);
    expect(completa.body).toMatchObject({
      nombre_usuario: "nuevoadmin",
      registro_completo: true,
      email_verificado: true,
    });
    const repetida = await api("POST", "/api/v1/administradores/invitacion/validar", { token });
    expect(repetida.status).toBe(400);
    expect(repetida.body.error.mensaje).toBe(
      "El enlace no es válido o venció. Pide al root una invitación nueva.",
    );
  });

  it("reenviar invalida el enlace anterior y deja vigente el nuevo (HU-10)", async () => {
    const { admin, token } = await invitar("otroadmin");
    const reenvio = await api("POST", `/api/v1/administradores/${admin.id}/invitacion`);
    expect(reenvio.status).toBe(200);
    expect(
      (await api("POST", "/api/v1/administradores/invitacion/validar", { token })).status,
    ).toBe(400);
    const nueva = db.invitaciones.find((i) => i.admin_id === admin.id && !i.usado);
    expect(nueva).toBeDefined();
    expect(
      (
        await api("POST", "/api/v1/administradores/invitacion/validar", {
          token: nueva!.token,
        })
      ).status,
    ).toBe(200);
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
      lugar_nacimiento: { pais: "CO", municipio: "66001", ciudad: null },
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
      lugar_nacimiento: { pais: "ES", municipio: null, ciudad: "x".repeat(121) },
    });
    expect(largo.body.error.campos["lugar_nacimiento.ciudad"]).toBe("Es demasiado largo.");

    expect((await api("PUT", "/api/v1/usuarios/me/perfil", edicion)).status).toBe(200);
  });

  it("valida los datos personales del registro del administrador antes de sus reglas de negocio (HU-12, RF-03)", async () => {
    const { token } = await invitar("juanadmin");
    const registro = {
      token,
      tipo_documento: "CC",
      numero_documento: "1088000222",
      nombres: "Juan",
      apellidos: "Torres",
      fecha_nacimiento: "1990-03-02",
      lugar_nacimiento: { pais: "CO", municipio: "76001", ciudad: null },
      direccion_facturacion: "Carrera 5 # 6-7",
      genero: "masculino",
      contrasena: "Nueva1234",
      confirmacion: "Nueva1234",
    };
    const invalido = await api("POST", "/api/v1/administradores/invitacion/completar", {
      ...registro,
      nombres: "1234",
    });
    expect(invalido.status).toBe(422);
    expect(invalido.body.error.codigo).toBe("datos_invalidos");
    expect(invalido.body.error.campos.nombres).toBe("El formato no es válido.");

    const espacios = await api("POST", "/api/v1/administradores/invitacion/completar", {
      ...registro,
      contrasena: "Nueva 1234",
      confirmacion: "Nueva 1234",
    });
    expect(espacios.body.error.campos.contrasena).toBe(
      "Mínimo 8 caracteres, con al menos una letra y un número, sin espacios.",
    );

    const completo = await api("POST", "/api/v1/administradores/invitacion/completar", registro);
    expect(completo.status).toBe(200);
    expect(completo.body.registro_completo).toBe(true);
  });

  // RF-03, SUP-43: «hoy» es 03/11/2026, así que el 02/11/1906 pasa de 120 años y el 03/11/1906 no.
  describe("edad máxima de la fecha de nacimiento (HU-01, HU-07, HU-12, RF-03, SUP-43)", () => {
    const EDAD_MAXIMA = "Revisa la fecha: la edad máxima es 120 años.";

    beforeEach(() => {
      vi.useFakeTimers({ toFake: ["Date"] });
      vi.setSystemTime(new Date("2026-11-03T15:00:00Z"));
    });
    afterEach(() => vi.useRealTimers());

    it("rechaza en el registro una fecha de hace más de 120 años y una futura", async () => {
      const cliente = {
        tipo_documento: "CC",
        numero_documento: "1088000333",
        nombres: "Ana",
        apellidos: "Ríos",
        fecha_nacimiento: "1906-11-02",
        lugar_nacimiento: { pais: "CO", municipio: "66001", ciudad: null },
        direccion_facturacion: "Calle 1 # 2-3",
        genero: "femenino",
        email: "ana.rios@correo.co",
        nombre_usuario: "anarios",
        contrasena: "Clave1234",
        acepta_politica: true,
      };
      const antigua = await api("POST", "/api/v1/usuarios/registro", cliente);
      expect(antigua.status).toBe(422);
      expect(antigua.body.error.campos.fecha_nacimiento).toBe(EDAD_MAXIMA);

      const futura = await api("POST", "/api/v1/usuarios/registro", {
        ...cliente,
        fecha_nacimiento: "2026-11-04",
      });
      expect(futura.body.error.campos.fecha_nacimiento).toBe(
        "La fecha de nacimiento no puede ser futura.",
      );

      const limite = await api("POST", "/api/v1/usuarios/registro", {
        ...cliente,
        fecha_nacimiento: "1906-11-03",
      });
      expect(limite.status).toBe(201);
    });

    it("rechaza en el perfil una fecha de hace más de 120 años", async () => {
      await entrar("lauragomez");
      const { body: perfil } = await api("GET", "/api/v1/usuarios/me/perfil");
      const edicion = { ...perfil, telefono: "3101234567" };

      const antigua = await api("PUT", "/api/v1/usuarios/me/perfil", {
        ...edicion,
        fecha_nacimiento: "1906-11-02",
      });
      expect(antigua.status).toBe(422);
      expect(antigua.body.error.campos.fecha_nacimiento).toBe(EDAD_MAXIMA);

      const limite = await api("PUT", "/api/v1/usuarios/me/perfil", {
        ...edicion,
        fecha_nacimiento: "1906-11-03",
      });
      expect(limite.status).toBe(200);
    });

    it("rechaza en el registro del administrador una fecha de hace más de 120 años", async () => {
      const { token } = await invitar("edadadmin");
      const registro = {
        token,
        tipo_documento: "CC",
        numero_documento: "1088000444",
        nombres: "Juan",
        apellidos: "Torres",
        fecha_nacimiento: "1906-11-02",
        lugar_nacimiento: { pais: "CO", municipio: "76001", ciudad: null },
        direccion_facturacion: "Carrera 5 # 6-7",
        genero: "masculino",
        contrasena: "Nueva1234",
        confirmacion: "Nueva1234",
      };
      const antigua = await api("POST", "/api/v1/administradores/invitacion/completar", registro);
      expect(antigua.status).toBe(422);
      expect(antigua.body.error.campos.fecha_nacimiento).toBe(EDAD_MAXIMA);

      const limite = await api("POST", "/api/v1/administradores/invitacion/completar", {
        ...registro,
        fecha_nacimiento: "1906-11-03",
      });
      expect(limite.status).toBe(200);
    });
  });
});

// Iteración 2 (docs/api/iteracion-2.md). Los tests comparten el estado de los mocks: cada uno
// usa documentos propios y compara saldos de forma relativa.
const adulto = (numero_documento: string, clases: string[] = ["economica"]) => ({
  tipo_documento: "CC",
  numero_documento,
  nombres: "Daniel",
  apellidos: "Arango",
  fecha_nacimiento: "1990-08-15",
  genero: "masculino",
  telefono: "311 555 0188",
  email: "daniel.arango@correo.co",
  contacto_nombre: "Laura Gómez",
  contacto_telefono: "310 555 0192",
  clases,
});
const viaje = (vuelos: number[], viajeros: unknown[]) => ({
  tramos: vuelos.map((vuelo_id) => ({ vuelo_id })),
  viajeros,
});
type Item = {
  codigo: string;
  origen: { codigo: string };
  economica: { precio_vigente: number; agotada: boolean };
};

describe("API simulada de la iteración 2 (MSW)", () => {
  it("busca vuelos públicos con filtros combinados y rechaza rangos invertidos (HU-20)", async () => {
    const { status, body } = await api(
      "GET",
      "/api/v1/busqueda/vuelos?origen=PEI&precio_min=200000&precio_max=400000&clase=economica",
    );
    expect(status).toBe(200);
    expect(body.items.length).toBeGreaterThan(0);
    for (const v of body.items as Item[]) {
      expect(v.origen.codigo).toBe("PEI");
      expect(v.economica.precio_vigente).toBeGreaterThanOrEqual(200_000);
      expect(v.economica.precio_vigente).toBeLessThanOrEqual(400_000);
    }
    const codigos = (body.items as Item[]).map((v) => v.codigo);
    expect(codigos).not.toContain("STA-00044"); // cancelado
    expect((body.items as Item[]).find((v) => v.codigo === "STA-00157")?.economica.agotada).toBe(
      true,
    );

    const rango = await api("GET", "/api/v1/busqueda/vuelos?precio_min=400000&precio_max=200000");
    expect(rango.status).toBe(422);
    expect(rango.body.error).toMatchObject({ codigo: "rango_invalido" });
    expect(rango.body.error.campos.precio_max).toBeDefined();
  });

  it("ofrece solo regresos que salen después de la llegada de la ida (HU-21)", async () => {
    const regresos = (fecha: string, ida = 101) =>
      api("GET", `/api/v1/busqueda/regresos?vuelo_ida_id=${ida}&destino=CTG&fecha=${fecha}`);
    const codigos = async (fecha: string, ida?: number) =>
      ((await regresos(fecha, ida)).body.items as Item[]).map((v) => v.codigo);
    expect(await codigos("2027-04-15")).toEqual(["STA-00133"]);
    expect(await codigos("2027-04-22")).toEqual(["STA-00132"]);
    expect(await codigos("2027-04-15", 104)).toEqual([]);
    expect((await regresos("2027-04-14")).body.error.codigo).toBe("rango_invalido");
    expect((await regresos("2027-04-22", 9999)).status).toBe(404);
  });

  it("el carrito es del cliente y valida cupo y límite al agregar (HU-22)", async () => {
    expect((await api("GET", "/api/v1/carrito")).status).toBe(401);
    await entrar("cruiz");
    expect((await api("GET", "/api/v1/carrito")).status).toBe(403);
    await entrar("lauragomez");
    const agregar = (vuelo_id: number, clase: string, viajeros = 1) =>
      api("POST", "/api/v1/carrito/selecciones", { tramos: [{ vuelo_id, clase }], viajeros });
    expect((await agregar(158, "primera")).body.error.codigo).toBe("clase_agotada");
    expect((await agregar(135, "economica")).body.error.codigo).toBe("limite_tiquetes");
    expect((await agregar(44, "economica")).body.error.codigo).toBe("vuelo_no_disponible");
    const unaSilla = await agregar(159, "economica");
    expect(unaSilla.status).toBe(201);
    const cambio = await api("PATCH", `/api/v1/carrito/selecciones/${unaSilla.body.id}`, {
      viajeros: 2,
    });
    expect(cambio.body.error.codigo).toBe("clase_agotada");
    expect((await api("DELETE", `/api/v1/carrito/selecciones/${unaSilla.body.id}`)).status).toBe(
      204,
    );
  });

  it("advierte el cambio de precio y la falta de cupo antes de confirmar (HU-23)", async () => {
    await entrar("lauragomez");
    const { body } = await api("GET", "/api/v1/carrito");
    type Sel = {
      id: number;
      confirmable: boolean;
      avisos: { codigo: string }[];
      tramos: { precio_unitario: number; precio_al_agregar: number }[];
    };
    const sel = (id: number) => (body.selecciones as Sel[]).find((s) => s.id === id)!;
    expect(sel(71).avisos.map((a) => a.codigo)).toEqual(["precio_cambio"]);
    expect(sel(71).tramos[0]).toMatchObject({
      precio_al_agregar: 262_500,
      precio_unitario: 210_000,
    });
    expect(sel(71).confirmable).toBe(true);
    expect(sel(72).confirmable).toBe(false);
    expect(sel(73).tramos).toHaveLength(2);
    expect(sel(73)).toMatchObject({ subtotal: 11_700_000 });
  });

  it("reserva con las reglas de los viajeros (HU-24)", async () => {
    await entrar("pedrorios");
    expect(
      (await api("POST", "/api/v1/reservas", viaje([142], [adulto("1088000501")]))).body.error
        .codigo,
    ).toBe("correo_no_verificado");

    await entrar("lauragomez");
    const duplicado = await api("POST", "/api/v1/reservas", viaje([131], [adulto("42118907")]));
    expect(duplicado.status).toBe(409);
    expect(duplicado.body.error).toMatchObject({
      codigo: "viajero_duplicado",
      campos: {
        "viajeros.0.numero_documento": "Este documento ya tiene un tiquete activo en este vuelo.",
      },
    });
    const repetido = await api(
      "POST",
      "/api/v1/reservas",
      viaje([142], [adulto("1088000510"), adulto("1088000510")]),
    );
    expect(repetido.body.error).toMatchObject({
      codigo: "viajero_duplicado",
      campos: {
        "viajeros.1.numero_documento": "Este documento ya tiene un tiquete activo en este vuelo.",
      },
    });
    const menor = await api(
      "POST",
      "/api/v1/reservas",
      viaje([142], [{ ...adulto("1088000502"), fecha_nacimiento: "2012-05-02" }]),
    );
    expect(menor.body.error.codigo).toBe("menor_sin_adulto");
    const cumple18 = await api(
      "POST",
      "/api/v1/reservas",
      viaje([142], [{ ...adulto("1088000503"), fecha_nacimiento: "2009-04-14" }]),
    );
    expect(cumple18.status).toBe(201);
    expect(cumple18.body).toMatchObject({ tipo: "reserva", estado: "vigente" });
    expect(cumple18.body.codigo).toMatch(/^[A-HJ-NP-Z2-9]{6}$/);
    expect(
      Date.parse(cumple18.body.vence_en) - Date.parse(cumple18.body.creada_en),
    ).toBeLessThanOrEqual(24 * 3_600_000);
  });

  it("compra en dos pasos: bloquea, confirma o rechaza sin cobrar (HU-25)", async () => {
    await entrar("lauragomez");
    const antes = (await api("GET", "/api/v1/monedero")).body.saldo;
    const pagada = await api("POST", "/api/v1/compras/901/confirmar");
    expect(pagada.body).toMatchObject({ estado: "activa", codigo: "K7Q2PX", total_pendiente: 0 });
    expect((await api("GET", "/api/v1/monedero")).body.saldo).toBe(antes - 800_000);
    expect((await api("POST", "/api/v1/compras/901/confirmar")).body.error.codigo).toBe(
      "estado_invalido",
    );
    expect((await api("POST", "/api/v1/compras/902/confirmar")).body.error.codigo).toBe(
      "bloqueo_vencido",
    );

    await entrar("sofiamarin");
    const compra = await api(
      "POST",
      "/api/v1/compras",
      viaje([101], [adulto("1088456789", ["primera"])]),
    );
    expect(compra.body).toMatchObject({ tipo: "compra", estado: "pendiente" });
    const sinSaldo = await api("POST", `/api/v1/compras/${compra.body.id}/confirmar`);
    expect(sinSaldo.body.error.codigo).toBe("saldo_insuficiente");
    expect((await api("GET", "/api/v1/monedero")).body.saldo).toBe(0);
    expect((await api("DELETE", `/api/v1/compras/${compra.body.id}`)).status).toBe(204);
    expect((await api("GET", `/api/v1/compras/${compra.body.id}`)).body.estado).toBe("cancelada");
  });

  it("reserva un trayecto completo con clase por tramo bajo un solo código (HU-26)", async () => {
    await entrar("lauragomez");
    const completo = await api(
      "POST",
      "/api/v1/reservas",
      viaje([101, 132], [adulto("1088000504", ["primera", "economica"])]),
    );
    expect(completo.status).toBe(201);
    expect(completo.body.tramos).toHaveLength(2);
    expect(completo.body.viajeros[0].tiquetes).toHaveLength(2);
    expect(completo.body.total).toBe(4_100_000 + 1_750_000);
    const alReves = await api(
      "POST",
      "/api/v1/reservas",
      viaje([101, 129], [adulto("1088000505", ["economica", "economica"])]),
    );
    expect(alReves.body.error.codigo).toBe("regreso_invalido");
  });

  it("paga una reserva por viajero al precio congelado y rechaza las vencidas (HU-27)", async () => {
    await entrar("lauragomez");
    await api("POST", "/api/v1/monedero/recargas", { tarjeta_id: 21, valor: 2_000_000 });
    expect(
      (await api("POST", "/api/v1/reservas/41/pagar", { viajero_ids: [4103] })).body.error.codigo,
    ).toBe("menor_sin_adulto");
    const pago = await api("POST", "/api/v1/reservas/41/pagar", { viajero_ids: [4101, 4102] });
    expect(pago.status).toBe(200);
    // Precio congelado: $ 262.500 aunque hoy STA-00131 cueste $ 210.000.
    expect(pago.body.compra).toMatchObject({
      tipo: "compra",
      estado: "activa",
      codigo: "H4N8WQ",
      total: 525_000,
    });
    expect(pago.body.reserva).toMatchObject({ estado: "vigente", total_pendiente: 262_500 });
    expect((await api("POST", "/api/v1/reservas/42/pagar", {})).body.error.codigo).toBe(
      "reserva_no_vigente",
    );
    const compras = await api("GET", "/api/v1/mis-viajes?tipo=compra");
    expect((compras.body.items as Item[]).map((v) => v.codigo)).toContain("H4N8WQ");
  });

  it("registra tarjetas con Luhn y vencimiento y recarga el valor exacto (HU-28, HU-30)", async () => {
    await entrar("sofiamarin");
    const tarjeta = {
      tipo: "credito",
      titular: "SOFIA MARIN",
      numero: "4242424242424241",
      vencimiento: "08/28",
      cvv: "123",
    };
    const luhn = await api("POST", "/api/v1/monedero/tarjetas", tarjeta);
    expect(luhn.status).toBe(422);
    expect(luhn.body.error).toMatchObject({
      codigo: "tarjeta_invalida",
      campos: { numero: "El número no es válido. Revisa los dígitos." },
    });
    const vencida = await api("POST", "/api/v1/monedero/tarjetas", {
      ...tarjeta,
      numero: "4242424242424242",
      vencimiento: "01/20",
    });
    expect(vencida.body.error.codigo).toBe("tarjeta_vencida");
    const nueva = await api("POST", "/api/v1/monedero/tarjetas", {
      ...tarjeta,
      numero: "4242424242424242",
    });
    expect(nueva.status).toBe(201);
    expect(nueva.body).toMatchObject({
      numero_enmascarado: "**** 4242",
      franquicia: "visa",
      vencida: false,
    });
    expect(JSON.stringify(nueva.body)).not.toContain("4242424242424242"); // RNF-12
    const cero = await api("POST", "/api/v1/monedero/recargas", {
      tarjeta_id: nueva.body.id,
      valor: 0,
    });
    expect(cero.body.error.campos.valor).toBe("Debe ser mayor que 0.");
    const antes = (await api("GET", "/api/v1/monedero")).body.saldo;
    const recarga = await api("POST", "/api/v1/monedero/recargas", {
      tarjeta_id: nueva.body.id,
      valor: 500_000,
    });
    expect(recarga.body).toMatchObject({
      tipo: "recarga",
      valor: 500_000,
      referencia: "**** 4242",
    });
    expect((await api("GET", "/api/v1/monedero")).body.saldo).toBe(antes + 500_000);
  });

  it("elimina tarjetas sin perder la referencia de sus recargas y filtra movimientos (HU-29, HU-31)", async () => {
    await entrar("lauragomez");
    expect(
      (await api("POST", "/api/v1/monedero/recargas", { tarjeta_id: 23, valor: 100_000 })).body
        .error.codigo,
    ).toBe("tarjeta_vencida");
    expect((await api("DELETE", "/api/v1/monedero/tarjetas/22")).status).toBe(204);
    const tarjetas = (await api("GET", "/api/v1/monedero/tarjetas")).body as { id: number }[];
    expect(tarjetas.map((t) => t.id)).not.toContain(22);
    const recargas = (await api("GET", "/api/v1/monedero/movimientos?tipo=recarga")).body.items as {
      tipo: string;
      referencia: string;
    }[];
    expect(recargas.every((m) => m.tipo === "recarga")).toBe(true);
    expect(recargas.map((m) => m.referencia)).toContain("**** 5100");
    const { body } = await api(
      "GET",
      "/api/v1/monedero/movimientos?desde=2026-10-01&hasta=2026-09-01",
    );
    expect(body.error.codigo).toBe("rango_invalido");
  });
});
