import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PromocionesPage } from "@/pages/promociones";
import { ADMIN, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";
import { BOG, PEI, resumenCiudad } from "@/test/vuelos";

const rutas = [
  { path: "/admin/promociones", element: <PromocionesPage /> },
  { path: "/admin/vuelos", element: <p>Vuelos programados</p> },
];

const SESION = "GET /api/v1/auth/me";
const LISTA = "GET /api/v1/promociones";

const promocion = (id: number, cambios: Record<string, unknown> = {}) => ({
  id,
  porcentaje: 40,
  clases: ["economica"],
  inicio: "2026-10-15T15:00:00Z",
  fin: "2026-10-15T17:00:00Z",
  estado: "vigente",
  vuelo_id: 76,
  vuelo_codigo: "STA-00076",
  origen: resumenCiudad(BOG),
  destino: resumenCiudad(PEI),
  salida: "2026-12-16T03:00:00Z",
  creada_en: "2026-10-14T12:00:00Z",
  ...cambios,
});

const pagina = (items: unknown[], total = items.length) => ({
  status: 200,
  body: { items, total, pagina: 1, por_pagina: 10 },
});

function consultas() {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => new URL((r as Request).url))
    .filter((u) => u.pathname === "/api/v1/promociones");
}

describe("Promociones (HU-17)", () => {
  it("lista las promociones con su descuento, clases, vigencia en hora de Colombia y estado", async () => {
    responderApi({
      [SESION]: sesionDe(ADMIN),
      [LISTA]: pagina([
        promocion(1),
        promocion(2, {
          vuelo_codigo: "STA-00090",
          clases: ["economica", "primera"],
          porcentaje: 15,
          inicio: "2026-10-20T15:00:00Z",
          fin: "2026-10-22T17:30:00Z",
          estado: "programada",
        }),
      ]),
    });
    renderRutas(rutas, "/admin/promociones");

    const primera = within(await screen.findByRole("row", { name: /STA-00076/ }));
    expect(primera.getByText("Bogotá → Pereira")).toBeVisible();
    expect(primera.getByText("40 %")).toBeVisible();
    expect(primera.getByText("Económica")).toBeVisible();
    expect(primera.getByText("15/10/2026 10:00 → 12:00")).toBeVisible();
    expect(primera.getByText("Vigente")).toBeVisible();

    const segunda = within(screen.getByRole("row", { name: /STA-00090/ }));
    expect(segunda.getByText("Económica y Primera")).toBeVisible();
    expect(segunda.getByText("20/10/2026 10:00 → 22/10/2026 12:30")).toBeVisible();
    expect(segunda.getByText("Programada")).toBeVisible();
  });

  it("filtra por estado y lo deja en la dirección", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina([promocion(1)]) });
    const { router } = renderRutas(rutas, "/admin/promociones");
    await screen.findByRole("row", { name: /STA-00076/ });

    await userEvent.setup().selectOptions(screen.getByLabelText("Estado"), "vencida");

    await waitFor(() => expect(consultas().at(-1)!.searchParams.get("estado")).toBe("vencida"));
    expect(router.state.location.search).toBe("?estado=vencida");
  });

  it("sin promociones lo dice según el filtro", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina([]) });
    renderRutas(rutas, "/admin/promociones?estado=agotada");
    expect(await screen.findByText("No hay promociones en este estado.")).toBeVisible();
  });

  it("sin promociones ni filtro explica cómo crear una", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina([]) });
    renderRutas(rutas, "/admin/promociones");

    expect(await screen.findByText("Todavía no hay promociones.")).toBeVisible();
    await userEvent.setup().click(screen.getByRole("link", { name: "Ir a vuelos programados" }));
    expect(await screen.findByText("Vuelos programados")).toBeVisible();
  });

  it("pagina el listado", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina([promocion(1)], 25) });
    renderRutas(rutas, "/admin/promociones");
    await screen.findByRole("row", { name: /STA-00076/ });

    await userEvent.setup().click(screen.getByRole("button", { name: "Página 2" }));

    await waitFor(() => expect(consultas().at(-1)!.searchParams.get("pagina")).toBe("2"));
  });
});
