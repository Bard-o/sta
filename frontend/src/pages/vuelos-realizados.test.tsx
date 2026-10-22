import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VuelosRealizadosPage } from "@/pages/vuelos-realizados";
import { ADMIN, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";
import { BOG, ciudad, pagina, resumenCiudad, vueloAdmin } from "@/test/vuelos";

const MAD = ciudad("MAD", "Madrid", "internacional", "Europe/Madrid");

const rutas = [{ path: "/admin/vuelos-realizados", element: <VuelosRealizadosPage /> }];

const SESION = "GET /api/v1/auth/me";
const LISTA = "GET /api/v1/vuelos";
const PASAJEROS_12 = "GET /api/v1/vuelos/12/pasajeros";

const realizado = (cambios: Parameters<typeof vueloAdmin>[0] = {}) =>
  vueloAdmin({
    estado: "realizado",
    editable: false,
    cancelable: false,
    motivo_no_editable: "El vuelo ya se realizó o está cancelado.",
    ...cambios,
  });

/** Pereira → Bogotá, llegó 29/09/2026 08:55; 25 + 113 tiquetes vendidos. */
const VUELO_12 = realizado({
  id: 12,
  codigo: "STA-00012",
  salida: "2026-09-29T13:05:00Z",
  llegada: "2026-09-29T13:55:00Z",
  tiquetes_vendidos: 138,
  ocupacion: {
    primera: { capacidad: 25, vendidas: 25, reservadas: 0, disponibles: 0 },
    economica: { capacidad: 125, vendidas: 113, reservadas: 0, disponibles: 12 },
  },
});

/** Bogotá → Madrid, llegó 28/09/2026 15:00 en Madrid (13:00Z, UTC+2). */
const VUELO_9 = realizado({
  id: 9,
  codigo: "STA-00009",
  tipo: "internacional",
  origen: resumenCiudad(BOG),
  destino: resumenCiudad(MAD),
  salida: "2026-09-28T03:00:00Z",
  llegada: "2026-09-28T13:00:00Z",
  duracion_minutos: 600,
  capacidad: { primera: 50, economica: 200, total: 250 },
  ocupacion: {
    primera: { capacidad: 50, vendidas: 41, reservadas: 0, disponibles: 9 },
    economica: { capacidad: 200, vendidas: 190, reservadas: 0, disponibles: 10 },
  },
});

const PASAJEROS = {
  status: 200,
  body: {
    vuelo: VUELO_12,
    ocupacion: VUELO_12.ocupacion,
    pasajeros: [
      { nombres: "Ana", apellidos: "Pérez", clase: "economica", silla: "12C", numero_silla: 58 },
      { nombres: "Luis", apellidos: "Mora", clase: "primera", silla: "2A", numero_silla: 3 },
    ],
  },
};

function consultas() {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => new URL((r as Request).url))
    .filter((u) => u.pathname === "/api/v1/vuelos");
}

const servidor = (extra: Record<string, unknown> = {}) =>
  responderApi({
    [SESION]: sesionDe(ADMIN),
    [LISTA]: pagina([VUELO_12, VUELO_9]),
    [PASAJEROS_12]: PASAJEROS,
    ...extra,
  } as Parameters<typeof responderApi>[0]);

const fila = (codigo: string) => screen.getByRole("row", { name: new RegExp(codigo) });

describe("S12 · Vuelos realizados (HU-18)", () => {
  it("lista los vuelos realizados con su llegada en la hora local del destino", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos-realizados");

    const primero = within(await screen.findByRole("row", { name: /STA-00012/ }));
    expect(primero.getByText("29/09/2026 08:55")).toBeVisible();
    expect(primero.getByText("Pereira → Bogotá")).toBeVisible();
    expect(primero.getByText("138 / 150")).toBeVisible();

    const madrid = within(fila("STA-00009"));
    expect(madrid.getByText("28/09/2026 15:00")).toBeVisible();
    expect(madrid.getByText("231 / 250")).toBeVisible();
    expect(consultas()[0].searchParams.get("estado")).toBe("realizado");
  });

  it("filtra por fecha de llegada, ruta o código", async () => {
    servidor();
    const { router } = renderRutas(rutas, "/admin/vuelos-realizados");
    const user = userEvent.setup();
    await screen.findByRole("row", { name: /STA-00012/ });

    await user.type(screen.getByLabelText("Llegada desde"), "2026-09-01");
    await user.type(screen.getByLabelText("Llegada hasta"), "2026-09-30");
    await user.type(screen.getByLabelText("Ruta o código"), "Madrid");

    await waitFor(() => {
      const ultima = consultas().at(-1)!;
      expect(ultima.searchParams.get("desde")).toBe("2026-09-01");
      expect(ultima.searchParams.get("hasta")).toBe("2026-09-30");
      expect(ultima.searchParams.get("q")).toBe("Madrid");
      expect(ultima.searchParams.get("estado")).toBe("realizado");
    });
    expect(router.state.location.search).toContain("desde=2026-09-01");
  });

  it("al elegir un vuelo muestra sus pasajeros con su clase y su silla, y la ocupación", async () => {
    servidor();
    const { router } = renderRutas(rutas, "/admin/vuelos-realizados");
    const user = userEvent.setup();
    await screen.findByRole("row", { name: /STA-00012/ });
    expect(screen.getByText(/Elige un vuelo de la lista/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Ver pasajeros de STA-00012" }));

    expect(await screen.findByRole("heading", { name: "Pasajeros de STA-00012" })).toBeVisible();
    expect(screen.getByText("Primera: 25 de 25 vendidas")).toBeVisible();
    expect(screen.getByText("Económica: 113 de 125 vendidas")).toBeVisible();
    const ana = within(screen.getByRole("row", { name: /Ana Pérez/ }));
    expect(ana.getByText("Económica")).toBeVisible();
    expect(ana.getByText("12C")).toBeVisible();
    const luis = within(screen.getByRole("row", { name: /Luis Mora/ }));
    expect(luis.getByText("Primera")).toBeVisible();
    expect(luis.getByText("2A")).toBeVisible();
    expect(router.state.location.search).toBe("?vuelo=12");
    expect(fila("STA-00012")).toHaveClass("is-hl");
  });

  it("abre directo el vuelo que trae la dirección", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos-realizados?vuelo=12");

    expect(await screen.findByRole("row", { name: /Ana Pérez/ })).toBeVisible();
  });

  it("un vuelo sin pasajeros lo dice y aun así muestra la ocupación", async () => {
    servidor({
      [PASAJEROS_12]: { status: 200, body: { ...PASAJEROS.body, pasajeros: [] } },
    });
    renderRutas(rutas, "/admin/vuelos-realizados?vuelo=12");

    expect(await screen.findByText("Este vuelo no tiene pasajeros registrados.")).toBeVisible();
    expect(screen.getByText("Primera: 25 de 25 vendidas")).toBeVisible();
  });

  it("si el vuelo no existe, lo explica en el panel", async () => {
    servidor({
      [PASAJEROS_12]: {
        status: 404,
        body: { error: { codigo: "no_encontrado", mensaje: "El vuelo no existe." } },
      },
    });
    renderRutas(rutas, "/admin/vuelos-realizados?vuelo=12");

    expect(await screen.findByText("El vuelo no existe.")).toBeVisible();
  });

  it("sin resultados lo dice según haya filtros o no", async () => {
    servidor({ [LISTA]: pagina([]) });
    renderRutas(rutas, "/admin/vuelos-realizados?q=Mitú");
    expect(await screen.findByText("No hay vuelos realizados con estos filtros.")).toBeVisible();
  });

  it("sin vuelos ni filtros lo dice", async () => {
    servidor({ [LISTA]: pagina([]) });
    renderRutas(rutas, "/admin/vuelos-realizados");
    expect(await screen.findByText("Todavía no hay vuelos realizados.")).toBeVisible();
  });

  it("un periodo con fin anterior al inicio se corrige antes de consultar", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos-realizados?desde=2026-09-30&hasta=2026-09-01");

    expect(
      await screen.findByText("La fecha final no puede ser anterior a la inicial."),
    ).toBeVisible();
    expect(consultas()).toHaveLength(0);
  });

  it("pagina el listado", async () => {
    servidor({ [LISTA]: pagina([VUELO_12], 25) });
    renderRutas(rutas, "/admin/vuelos-realizados");
    await screen.findByRole("row", { name: /STA-00012/ });

    await userEvent.setup().click(screen.getByRole("button", { name: "Página 2" }));

    await waitFor(() => expect(consultas().at(-1)!.searchParams.get("pagina")).toBe("2"));
  });
});
