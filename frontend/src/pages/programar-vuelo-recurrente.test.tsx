import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schemas } from "@/api/client";
import { ProgramarVueloPage } from "@/pages/programar-vuelo";
import { ADMIN, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [{ path: "/admin/vuelos/nuevo", element: <ProgramarVueloPage /> }];

const ciudad = (
  codigo: string,
  nombre: string,
  tipo: "nacional" | "internacional",
  zona = "America/Bogota",
): Schemas["Ciudad"] => ({
  codigo,
  nombre,
  pais: "Colombia",
  zona_horaria: zona,
  tipo,
  habilitada_internacional: true,
  imagen_url: `/imagenes/ciudades/${codigo}.jpg`,
});

const PEI = ciudad("PEI", "Pereira", "nacional");
const BOG = ciudad("BOG", "Bogotá", "nacional");
const resumen = (c: Schemas["Ciudad"]) => ({
  codigo: c.codigo,
  nombre: c.nombre,
  zona_horaria: c.zona_horaria,
});

const SESION = "GET /api/v1/auth/me";
const CIUDADES_API = "GET /api/v1/ciudades";
const VISTA = "POST /api/v1/vuelos/vista-previa";
const VISTA_SERIE = "POST /api/v1/vuelos/recurrentes/vista-previa";
const PUBLICAR_SERIE = "POST /api/v1/vuelos/recurrentes";

const OMITIDA = {
  fecha: "2026-10-19",
  codigo: "vuelo_duplicado",
  motivo: "Ya existe un vuelo igual.",
};

/** Dos lunes y una fecha omitida: el resumen dice «2 vuelos los lunes. 1 fecha omitida…». */
const SERIE_VISTA = {
  status: 200,
  body: {
    tipo: "nacional",
    capacidad: { primera: 25, economica: 125, total: 150 },
    fechas: ["2026-10-05", "2026-10-12"],
    omitidas: [OMITIDA],
  },
};

/** Pereira → Bogotá, 06:00 (11:00Z), 50 min. */
const VISTA_VUELO = {
  status: 200,
  body: {
    tipo: "nacional",
    origen: resumen(PEI),
    destino: resumen(BOG),
    salida: "2026-10-05T11:00:00Z",
    llegada: "2026-10-05T11:50:00Z",
    duracion_minutos: 50,
    capacidad: { primera: 25, economica: 125, total: 150 },
  },
};

const creado = (id: number, salida: string) => ({
  id,
  codigo: `STA-${String(id).padStart(5, "0")}`,
  origen: resumen(PEI),
  destino: resumen(BOG),
  salida,
});

const SERIE_CREADA = {
  status: 201,
  body: {
    creados: [creado(93, "2026-10-05T11:00:00Z"), creado(94, "2026-10-12T11:00:00Z")],
    omitidas: [OMITIDA],
  },
};

const servidor = (extra: Record<string, unknown> = {}) =>
  responderApi({
    [SESION]: sesionDe(ADMIN),
    [CIUDADES_API]: { status: 200, body: [PEI, BOG] },
    [VISTA]: VISTA_VUELO,
    [VISTA_SERIE]: SERIE_VISTA,
    [PUBLICAR_SERIE]: SERIE_CREADA,
    ...extra,
  } as Parameters<typeof responderApi>[0]);

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

beforeEach(() => {
  // Solo la fecha: «hoy» es 01/06/2026 y el límite de 12 meses, 01/06/2027.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-06-01T12:00:00Z"));
});
afterEach(() => vi.useRealTimers());

async function llenarVuelo(user: ReturnType<typeof userEvent.setup>) {
  await screen.findAllByRole("option", { name: "Bogotá (BOG)" });
  await user.selectOptions(screen.getByLabelText("Origen", { exact: true }), "PEI");
  await user.selectOptions(screen.getByLabelText("Destino", { exact: true }), "BOG");
  await user.type(screen.getByLabelText(/^Hora de salida/), "06:00");
  await user.type(screen.getByLabelText("Horas"), "0");
  await user.clear(screen.getByLabelText("Minutos"));
  await user.type(screen.getByLabelText("Minutos"), "50");
  await user.type(screen.getByLabelText("Precio por persona, económica"), "280000");
  await user.type(screen.getByLabelText("Precio por persona, primera"), "750000");
}

async function llenarSerie(
  user: ReturnType<typeof userEvent.setup>,
  { dias = ["lunes"], desde = "2026-10-01", hasta = "2026-12-31" } = {},
) {
  await llenarVuelo(user);
  await user.click(screen.getByRole("switch", { name: "Se repite" }));
  for (const dia of dias) await user.click(screen.getByRole("button", { name: dia }));
  await user.clear(screen.getByLabelText("Desde"));
  await user.type(screen.getByLabelText("Desde"), desde);
  await user.type(screen.getByLabelText("Hasta"), hasta);
}

const publicar = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: "Publicar vuelos" }));

describe("S08 · Vuelos recurrentes (HU-14)", () => {
  it("«Se repite» cambia la fecha de salida por los días y el periodo", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await screen.findByLabelText("Fecha de salida");
    await user.type(screen.getByLabelText("Fecha de salida"), "2026-10-05");

    expect(screen.getByRole("switch", { name: "Se repite" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.queryByLabelText("Desde")).not.toBeInTheDocument();

    await user.click(screen.getByRole("switch", { name: "Se repite" }));

    expect(screen.queryByLabelText("Fecha de salida")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-10-05");
    expect(screen.getByLabelText("Hasta")).toBeVisible();
    expect(screen.getByText("Máximo 12 meses desde hoy.")).toBeVisible();
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(7);
    expect(screen.getByRole("button", { name: "Publicar vuelos" })).toBeVisible();
  });

  it("la vista previa resume la serie y muestra el pase de la primera fecha", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await llenarSerie(user);

    const linea = await screen.findByText(/Repeticiones:/, {}, { timeout: 3000 });
    expect(linea.parentElement).toHaveTextContent(
      "2 vuelos los lunes. 1 fecha omitida porque ya existe un vuelo igual.",
    );
    expect(await peticiones(VISTA_SERIE)[0].json()).toEqual({
      origen: "PEI",
      destino: "BOG",
      hora_salida: "06:00",
      duracion_minutos: 50,
      precio_economica: 280000,
      precio_primera: 750000,
      dias_semana: ["lun"],
      desde: "2026-10-01",
      hasta: "2026-12-31",
    });
    // El pase se calcula con la primera fecha que sí se crearía.
    await waitFor(() => expect(peticiones(VISTA)).toHaveLength(1));
    expect((await peticiones(VISTA)[0].json()).fecha_salida).toBe("2026-10-05");
    expect(screen.getByText("STA-?????")).toBeVisible();
  });

  it("si ninguna fecha se puede crear, lo dice en la vista previa", async () => {
    servidor({
      [VISTA_SERIE]: {
        status: 200,
        body: { ...SERIE_VISTA.body, fechas: [], omitidas: [OMITIDA] },
      },
    });
    renderRutas(rutas, "/admin/vuelos/nuevo");
    await llenarSerie(userEvent.setup());

    expect(
      await screen.findByText(/no se crearía ningún vuelo/, {}, { timeout: 3000 }),
    ).toBeVisible();
    expect(peticiones(VISTA)).toHaveLength(0);
  });

  it("publica la serie y lista los vuelos creados y las fechas omitidas con su motivo", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await llenarSerie(user);
    await publicar(user);

    expect(
      await screen.findByText(/Publicamos 2 vuelos \(Pereira → Bogotá\) los lunes\./),
    ).toBeVisible();
    const creados = screen.getByRole("region", { name: "Vuelos creados" });
    expect(
      within(creados)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["STA-00093 · 05/10/2026 06:00", "STA-00094 · 12/10/2026 06:00"]);
    const omitidas = screen.getByRole("region", { name: "Fechas omitidas" });
    expect(within(omitidas).getByRole("listitem")).toHaveTextContent(
      "19/10/2026 · Ya existe un vuelo igual.",
    );
    expect(await peticiones(PUBLICAR_SERIE)[0].json()).toMatchObject({
      dias_semana: ["lun"],
      desde: "2026-10-01",
      hasta: "2026-12-31",
    });
    // El formulario queda limpio y sin «Se repite».
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Se repite" })).toHaveAttribute(
        "aria-checked",
        "false",
      ),
    );
  });

  it("los 7 días se envían como una serie diaria", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await llenarSerie(user, {
      dias: ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    });
    await publicar(user);

    await waitFor(() => expect(peticiones(PUBLICAR_SERIE)).toHaveLength(1));
    expect((await peticiones(PUBLICAR_SERIE)[0].json()).dias_semana).toHaveLength(7);
  });

  it.each([
    [
      "un periodo con fin anterior al inicio",
      { desde: "2026-12-01", hasta: "2026-10-01" },
      "La fecha final no puede ser anterior a la inicial.",
    ],
    [
      "un periodo de más de 12 meses",
      { desde: "2026-10-01", hasta: "2027-08-01" },
      "Máximo 12 meses desde hoy.",
    ],
  ])("rechaza %s junto a «Hasta» y no guarda", async (_caso, periodo, mensaje) => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await llenarSerie(user, periodo);
    await publicar(user);

    expect(await screen.findByText(mensaje)).toBeVisible();
    expect(screen.getByLabelText("Hasta")).toBeInvalid();
    expect(peticiones(PUBLICAR_SERIE)).toHaveLength(0);
  });

  it("pide elegir al menos un día", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await llenarSerie(user, { dias: [] });
    await publicar(user);

    expect(await screen.findByText("Elige al menos un día de la semana.")).toBeVisible();
    expect(peticiones(PUBLICAR_SERIE)).toHaveLength(0);
  });

  it("un error del servidor sobre el periodo se muestra junto a «Hasta»", async () => {
    servidor({
      [PUBLICAR_SERIE]: {
        status: 422,
        body: {
          error: {
            codigo: "datos_invalidos",
            mensaje: "Hay datos inválidos.",
            campos: { hasta: "El periodo no puede pasar de 12 meses." },
          },
        },
      },
    });
    renderRutas(rutas, "/admin/vuelos/nuevo");
    const user = userEvent.setup();
    await llenarSerie(user);
    await publicar(user);

    expect(await screen.findByText("El periodo no puede pasar de 12 meses.")).toBeVisible();
    expect(screen.getByLabelText("Hasta")).toBeInvalid();
  });
});
