import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuevaPromocionPage } from "@/pages/nueva-promocion";
import { ADMIN, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";
import { BOG, ciudad, resumenCiudad, vueloAdmin } from "@/test/vuelos";

const MAD = ciudad("MAD", "Madrid", "internacional", "Europe/Madrid");

const rutas = [
  { path: "/admin/vuelos/:vueloId/promocion", element: <NuevaPromocionPage /> },
  { path: "/admin/promociones", element: <p>Lista de promociones</p> },
];

const SESION = "GET /api/v1/auth/me";
const GESTION = "GET /api/v1/vuelos/76/gestion";
const CREAR = "POST /api/v1/vuelos/76/promociones";

/** Bogotá → Madrid, internacional, con 41 de 50 en primera y 58 de 200 en económica. */
const VUELO_76 = vueloAdmin({
  id: 76,
  codigo: "STA-00076",
  tipo: "internacional",
  origen: resumenCiudad(BOG),
  destino: resumenCiudad(MAD),
  salida: "2026-12-16T03:00:00Z",
  llegada: "2026-12-16T13:00:00Z",
  duracion_minutos: 600,
  precio_economica: 2450000,
  precio_primera: 6900000,
  capacidad: { primera: 50, economica: 200, total: 250 },
  ocupacion: {
    primera: { capacidad: 50, vendidas: 41, reservadas: 0, disponibles: 9 },
    economica: { capacidad: 200, vendidas: 58, reservadas: 0, disponibles: 142 },
  },
  tiquetes_vendidos: 99,
  editable: false,
  cancelable: false,
});

const CREADA = {
  status: 201,
  body: {
    id: 12,
    porcentaje: 40,
    clases: ["economica"],
    inicio: "2026-10-15T15:00:00Z",
    fin: "2026-10-15T17:00:00Z",
    estado: "programada",
    vuelo_id: 76,
    vuelo_codigo: "STA-00076",
    origen: resumenCiudad(BOG),
    destino: resumenCiudad(MAD),
    salida: "2026-12-16T03:00:00Z",
    creada_en: "2026-10-14T12:00:00Z",
  },
};

const servidor = (extra: Record<string, unknown> = {}) =>
  responderApi({
    [SESION]: sesionDe(ADMIN),
    [GESTION]: { status: 200, body: VUELO_76 },
    [CREAR]: CREADA,
    ...extra,
  } as Parameters<typeof responderApi>[0]);

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

beforeEach(() => {
  // Solo la fecha: «ahora» es el 14/10/2026 07:00 en Colombia.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-14T12:00:00Z"));
});
afterEach(() => vi.useRealTimers());

async function abrir() {
  renderRutas(rutas, "/admin/vuelos/76/promocion");
  await screen.findByRole("heading", { name: "Nueva promoción" });
  await screen.findByLabelText("Porcentaje");
  return userEvent.setup();
}

async function llenar(
  user: Awaited<ReturnType<typeof abrir>>,
  d: { porcentaje?: string; clases?: string[]; inicio?: string; fin?: string } = {},
) {
  const {
    porcentaje = "40",
    clases = ["económica"],
    inicio = "2026-10-15T10:00",
    fin = "2026-10-15T12:00",
  } = d;
  if (porcentaje) await user.type(screen.getByLabelText("Porcentaje"), porcentaje);
  for (const clase of clases) await user.click(screen.getByRole("button", { name: clase }));
  if (inicio) await user.type(screen.getByLabelText(/^Inicio/), inicio);
  if (fin) await user.type(screen.getByLabelText(/^Fin/), fin);
}

const publicar = (user: Awaited<ReturnType<typeof abrir>>) =>
  user.click(screen.getByRole("button", { name: "Publicar promoción" }));

describe("S11 · Nueva promoción (HU-17)", () => {
  it("muestra el vuelo y sus ventas por clase", async () => {
    servidor();
    await abrir();

    expect(screen.getByLabelText(/Vuelo STA-00076 Bogotá a Madrid/)).toBeVisible();
    expect(screen.getByText("$ 2.450.000")).toBeVisible();
    expect(screen.getByText("Primera: 41 de 50 vendidas")).toBeVisible();
    expect(screen.getByText("Económica: 58 de 200 vendidas")).toBeVisible();
    expect(screen.getByRole("meter", { name: "Primera: 41 de 50 vendidas" })).toHaveAttribute(
      "aria-valuenow",
      "41",
    );
  });

  it("calcula el precio con descuento para las sillas disponibles", async () => {
    servidor();
    const user = await abrir();
    await llenar(user);

    const resumen = screen.getByText(/Económica pasa de/).parentElement!;
    expect(resumen).toHaveTextContent(
      "Económica pasa de $ 2.450.000 a $ 1.470.000 para las 142 sillas disponibles.",
    );
  });

  it("con las dos clases resume cada una con su precio y sus sillas", async () => {
    servidor();
    const user = await abrir();
    await llenar(user, { porcentaje: "10", clases: ["económica", "primera"] });

    expect(screen.getByText(/Económica pasa de/).parentElement).toHaveTextContent(
      "a $ 2.205.000 para las 142 sillas disponibles.",
    );
    expect(screen.getByText(/Primera pasa de/).parentElement).toHaveTextContent(
      "Primera pasa de $ 6.900.000 a $ 6.210.000 para las 9 sillas disponibles.",
    );
  });

  it("publica con el desfase de Colombia y vuelve a la lista de promociones", async () => {
    servidor();
    const user = await abrir();
    await llenar(user);
    await publicar(user);

    expect(await screen.findByText("Lista de promociones")).toBeVisible();
    expect(await peticiones(CREAR)[0].json()).toEqual({
      porcentaje: 40,
      clases: ["economica"],
      inicio: "2026-10-15T10:00:00-05:00",
      fin: "2026-10-15T12:00:00-05:00",
    });
  });

  it.each([
    [
      "un porcentaje de 0",
      { porcentaje: "0" },
      "El porcentaje debe ser un número entero entre 1 y 90.",
    ],
    [
      "un porcentaje de 91",
      { porcentaje: "91" },
      "El porcentaje debe ser un número entero entre 1 y 90.",
    ],
    [
      "un porcentaje con decimales",
      { porcentaje: "12.5" },
      "El porcentaje debe ser un número entero entre 1 y 90.",
    ],
    ["ninguna clase", { clases: [] }, "Elige al menos una clase."],
    ["un fin igual al inicio", { fin: "2026-10-15T10:00" }, "El fin debe ser posterior al inicio."],
    [
      "un fin que ya pasó",
      { inicio: "2026-10-13T10:00", fin: "2026-10-14T06:00" },
      "El fin debe ser una fecha futura.",
    ],
  ])("rechaza %s junto al campo y no guarda", async (_caso, cambios, mensaje) => {
    servidor();
    const user = await abrir();
    await llenar(user, cambios);
    await publicar(user);

    expect(await screen.findByText(mensaje)).toBeVisible();
    expect(peticiones(CREAR)).toHaveLength(0);
  });

  it("pide el inicio y el fin si faltan", async () => {
    servidor();
    const user = await abrir();
    await llenar(user, { inicio: "", fin: "" });
    await publicar(user);

    expect(await screen.findByText("Escribe la fecha y la hora de inicio.")).toBeVisible();
    expect(screen.getByText("Escribe la fecha y la hora de fin.")).toBeVisible();
  });

  it("una clase que ya tiene promoción se rechaza: las promociones no se acumulan", async () => {
    servidor({
      [CREAR]: {
        status: 409,
        body: {
          error: {
            codigo: "promocion_duplicada",
            mensaje:
              "Este vuelo ya tiene una promoción programada en económica. Las promociones no se acumulan.",
            campos: { clases: "Ya hay una promoción vigente o programada para esta clase." },
          },
        },
      },
    });
    const user = await abrir();
    await llenar(user);
    await publicar(user);

    expect(await screen.findByText(/Las promociones no se acumulan\./)).toBeVisible();
    expect(
      screen.getByText("Ya hay una promoción vigente o programada para esta clase."),
    ).toBeVisible();
    expect(screen.queryByText("Lista de promociones")).not.toBeInTheDocument();
  });

  it("un vuelo cancelado no admite promociones", async () => {
    servidor({ [GESTION]: { status: 200, body: { ...VUELO_76, estado: "cancelado" } } });
    renderRutas(rutas, "/admin/vuelos/76/promocion");

    expect(await screen.findByText(/no admite promociones/)).toBeVisible();
    expect(screen.queryByLabelText("Porcentaje")).not.toBeInTheDocument();
  });

  it("un vuelo que ya salió tampoco", async () => {
    servidor({ [GESTION]: { status: 200, body: { ...VUELO_76, salida: "2026-10-14T10:00:00Z" } } });
    renderRutas(rutas, "/admin/vuelos/76/promocion");

    expect(await screen.findByText(/no admite promociones/)).toBeVisible();
  });

  it("un vuelo que no existe muestra «Página no encontrada»", async () => {
    servidor({
      [GESTION]: {
        status: 404,
        body: { error: { codigo: "no_encontrado", mensaje: "El vuelo no existe." } },
      },
    });
    renderRutas(rutas, "/admin/vuelos/76/promocion");

    await waitFor(() => expect(screen.getByText("Página no encontrada")).toBeVisible());
  });
});
