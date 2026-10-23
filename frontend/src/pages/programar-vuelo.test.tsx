import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schemas } from "@/api/client";
import { ProgramarVueloPage } from "@/pages/programar-vuelo";
import { ADMIN, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  { path: "/admin/vuelos/nuevo", element: <ProgramarVueloPage /> },
  { path: "/admin/vuelos", element: <p>Vuelos programados</p> },
];

const ciudad = (
  codigo: string,
  nombre: string,
  tipo: "nacional" | "internacional",
  zona = "America/Bogota",
): Schemas["Ciudad"] => ({
  codigo,
  nombre,
  pais: tipo === "nacional" ? "Colombia" : "Exterior",
  zona_horaria: zona,
  tipo,
  habilitada_internacional: ["BOG", "PEI"].includes(codigo),
  imagen_url: `/imagenes/ciudades/${codigo}.jpg`,
});

const CIUDADES = [
  ciudad("BOG", "Bogotá", "nacional"),
  ciudad("PEI", "Pereira", "nacional"),
  ciudad("MZL", "Manizales", "nacional"),
  ciudad("MAD", "Madrid", "internacional", "Europe/Madrid"),
  ciudad("MIA", "Miami", "internacional", "America/New_York"),
];

const SESION = "GET /api/v1/auth/me";
const CIUDADES_API = "GET /api/v1/ciudades";
const VISTA = "POST /api/v1/vuelos/vista-previa";
const PUBLICAR = "POST /api/v1/vuelos";

const resumen = (c: Schemas["Ciudad"]) => ({
  codigo: c.codigo,
  nombre: c.nombre,
  zona_horaria: c.zona_horaria,
});

/** Bogotá → Madrid, salida 10/12/2026 22:00 (03:00Z del 11), 10 h: llega 13:00Z = 14:00 en Madrid. */
const VISTA_BOG_MAD = {
  status: 200,
  body: {
    tipo: "internacional",
    origen: resumen(CIUDADES[0]),
    destino: resumen(CIUDADES[3]),
    salida: "2026-12-11T03:00:00Z",
    llegada: "2026-12-11T13:00:00Z",
    duracion_minutos: 600,
    capacidad: { primera: 50, economica: 200, total: 250 },
  },
};

const ERROR = (
  status: number,
  codigo: string,
  mensaje: string,
  campos?: Record<string, string>,
) => ({
  status,
  body: { error: { codigo, mensaje, campos } },
});

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

const servidor = (extra: Record<string, unknown> = {}) =>
  responderApi({
    [SESION]: sesionDe(ADMIN),
    [CIUDADES_API]: { status: 200, body: CIUDADES },
    [VISTA]: VISTA_BOG_MAD,
    ...extra,
  } as Parameters<typeof responderApi>[0]);

beforeEach(() => {
  // Solo la fecha: «hoy» es 01/06/2026; los temporizadores siguen reales (la vista previa espera).
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-06-01T12:00:00Z"));
});
afterEach(() => vi.useRealTimers());

/** El catálogo llega por red: hasta que carga, los selectores solo tienen la opción vacía. */
const esperarCiudades = () => screen.findAllByRole("option", { name: "Madrid (MAD)" });

async function llenar(
  datos: Partial<{
    origen: string;
    destino: string;
    fecha: string;
    hora: string;
    horas: string;
    minutos: string;
    economica: string;
    primera: string;
  }> = {},
) {
  const d = {
    origen: "BOG",
    destino: "MAD",
    fecha: "2026-12-10",
    hora: "22:00",
    horas: "10",
    minutos: "0",
    economica: "2450000",
    primera: "6900000",
    ...datos,
  };
  const user = userEvent.setup();
  await esperarCiudades();
  await user.selectOptions(await screen.findByLabelText("Origen", { exact: true }), d.origen);
  await user.selectOptions(screen.getByLabelText("Destino", { exact: true }), d.destino);
  await user.type(screen.getByLabelText("Fecha de salida"), d.fecha);
  await user.type(screen.getByLabelText(/^Hora de salida/), d.hora);
  await user.clear(screen.getByLabelText("Horas"));
  await user.type(screen.getByLabelText("Horas"), d.horas);
  await user.clear(screen.getByLabelText("Minutos"));
  await user.type(screen.getByLabelText("Minutos"), d.minutos);
  await user.type(screen.getByLabelText("Precio por persona, económica"), d.economica);
  await user.type(screen.getByLabelText("Precio por persona, primera"), d.primera);
  return user;
}

const publicar = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: "Publicar vuelo" }));

describe("S08 · Programar vuelo (HU-13)", () => {
  it("ofrece las ciudades del catálogo con su código", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");

    const origen = await screen.findByLabelText("Origen", { exact: true });
    expect(await screen.findAllByRole("option", { name: "Madrid (MAD)" })).toHaveLength(2);
    expect(origen).toHaveValue("");
  });

  it("la hora de salida dice en qué hora local se escribe, con su desfase", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();

    await esperarCiudades();
    await user.selectOptions(await screen.findByLabelText("Origen", { exact: true }), "BOG");
    expect(screen.getByLabelText("Hora de salida (hora de Bogotá, UTC-5)")).toBeVisible();
  });

  it("muestra la vista previa con la llegada en la hora local del destino (Madrid, UTC+1 en diciembre)", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    await llenar();

    expect(
      (await screen.findByText(/Llegada calculada:/, {}, { timeout: 3000 })).parentElement,
    ).toHaveTextContent("11/12/2026 14:00 en Madrid (UTC+1)");
    expect(screen.getByText(/Tipo:/).parentElement).toHaveTextContent(
      "internacional, 250 sillas (50 en primera, 200 en económica)",
    );
    expect(screen.getByText("STA-?????")).toBeVisible();
    expect(screen.getByText("$ 2.450.000")).toBeVisible();
    expect(await peticiones(VISTA)[0].json()).toEqual({
      origen: "BOG",
      destino: "MAD",
      fecha_salida: "2026-12-10",
      hora_salida: "22:00",
      duracion_minutos: 600,
      precio_economica: 2450000,
      precio_primera: 6900000,
    });
  });

  it("en verano la llegada cae en UTC+2 (10/07/2026 22:00 → 11/07/2026 15:00)", async () => {
    servidor({
      [VISTA]: {
        ...VISTA_BOG_MAD,
        body: {
          ...VISTA_BOG_MAD.body,
          salida: "2026-07-11T03:00:00Z",
          llegada: "2026-07-11T13:00:00Z",
        },
      },
    });
    renderRutas(rutas, "/admin/vuelos/nuevo");
    await llenar({ fecha: "2026-07-10" });

    expect(
      (await screen.findByText(/Llegada calculada:/, {}, { timeout: 3000 })).parentElement,
    ).toHaveTextContent("11/07/2026 15:00 en Madrid (UTC+2)");
  });

  it("no pide la vista previa mientras el formulario es inválido", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await esperarCiudades();
    await user.selectOptions(await screen.findByLabelText("Origen", { exact: true }), "BOG");

    expect(screen.getByText(/Completa el formulario con datos válidos/)).toBeVisible();
    expect(peticiones(VISTA)).toHaveLength(0);
  });

  it("publica el vuelo, informa el código y limpia el formulario", async () => {
    servidor({
      [PUBLICAR]: {
        status: 201,
        body: {
          id: 93,
          codigo: "STA-00093",
          origen: resumen(CIUDADES[0]),
          destino: resumen(CIUDADES[3]),
        },
      },
    });
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = await llenar();
    await publicar(user);

    expect(
      await screen.findByText(/Publicamos el vuelo STA-00093 \(Bogotá → Madrid\)/),
    ).toBeVisible();
    expect(
      screen.getByText(/su noticia y su imagen en el carrusel/, { selector: "div" }),
    ).toBeVisible();
    expect(await peticiones(PUBLICAR)[0].json()).toEqual({
      origen: "BOG",
      destino: "MAD",
      fecha_salida: "2026-12-10",
      hora_salida: "22:00",
      duracion_minutos: 600,
      precio_economica: 2450000,
      precio_primera: 6900000,
    });
    await waitFor(() => expect(screen.getByLabelText("Origen", { exact: true })).toHaveValue(""));
  });

  it.each([
    ["una salida en el pasado", { fecha: "2026-05-01" }, "La fecha de salida no puede ser pasada."],
    [
      "una duración de 0",
      { horas: "0", minutos: "0" },
      "La duración debe ser de más de 0 minutos y menos de 24 horas.",
    ],
    ["una duración de 24 horas", { horas: "24" }, "Las horas van de 0 a 23."],
    ["un precio de 0", { economica: "0" }, "El precio debe ser mayor que 0."],
    ["un origen igual al destino", { destino: "BOG" }, "El destino debe ser distinto del origen."],
  ])("rechaza %s junto al campo y no guarda", async (_caso, cambios, mensaje) => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = await llenar(cambios);
    await publicar(user);

    expect(await screen.findByText(mensaje)).toBeVisible();
    expect(peticiones(PUBLICAR)).toHaveLength(0);
  });

  it("una ruta no permitida (Manizales → Miami) se explica en la vista previa y junto al destino", async () => {
    const rechazo = ERROR(422, "ruta_no_permitida", "Esta ruta no está permitida.", {
      destino: "Las rutas internacionales salen de Pereira, Bogotá, Medellín, Cali o Cartagena.",
    });
    servidor({ [VISTA]: rechazo, [PUBLICAR]: rechazo });
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = await llenar({ origen: "MZL", destino: "MIA" });

    expect(
      await screen.findByText(/Destino: Las rutas internacionales salen de/, {}, { timeout: 3000 }),
    ).toBeVisible();
    await publicar(user);
    expect(
      await screen.findAllByText(
        "Las rutas internacionales salen de Pereira, Bogotá, Medellín, Cali o Cartagena.",
      ),
    ).not.toHaveLength(0);
    expect(screen.getByLabelText("Destino", { exact: true })).toBeInvalid();
  });

  it("un vuelo igual a la misma hora se rechaza junto a la hora de salida", async () => {
    const duplicado = ERROR(409, "vuelo_duplicado", "Ya existe un vuelo de esta ruta a esa hora.", {
      hora_salida: "Ya existe un vuelo de esta ruta a esa hora.",
    });
    servidor({ [PUBLICAR]: duplicado });
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = await llenar();
    await publicar(user);

    await waitFor(() => expect(screen.getByLabelText(/^Hora de salida/)).toBeInvalid());
    expect(
      screen.getAllByText("Ya existe un vuelo de esta ruta a esa hora.").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/Publicamos el vuelo/)).not.toBeInTheDocument();
  });

  it("da formato de pesos a los precios al salir del campo (IU-06)", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    const campo = await screen.findByLabelText("Precio por persona, económica");

    await user.type(campo, "2450000");
    await user.tab();

    expect(campo).toHaveValue("$ 2.450.000");
  });

  it("«Cancelar» vuelve a los vuelos programados", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");

    await userEvent.setup().click(await screen.findByRole("link", { name: "Cancelar" }));
    expect(await screen.findByText("Vuelos programados")).toBeVisible();
  });
});
