import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VuelosProgramadosPage } from "@/pages/vuelos-programados";
import { ADMIN, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";
import { conReservas, conTiquetes, pagina, vueloAdmin } from "@/test/vuelos";

const rutas = [
  { path: "/admin/vuelos", element: <VuelosProgramadosPage /> },
  { path: "/admin/vuelos/nuevo", element: <p>Formulario de programar vuelo</p> },
  { path: "/admin/vuelos/:vueloId/editar", element: <p>Formulario de edición</p> },
];

const SESION = "GET /api/v1/auth/me";
const LISTA = "GET /api/v1/vuelos";
const CANCELAR_51 = "POST /api/v1/vuelos/51/cancelar";

const VUELOS = [vueloAdmin(), conReservas(), conTiquetes()];

function consultas() {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => new URL((r as Request).url))
    .filter((u) => u.pathname === "/api/v1/vuelos");
}

const fila = (codigo: string) => screen.getByRole("row", { name: new RegExp(codigo) });

describe("S09 · Vuelos programados (HU-15, HU-16)", () => {
  it("lista los vuelos con su salida local, ruta, ocupación y estado", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    renderRutas(rutas, "/admin/vuelos");

    const libre = within(await screen.findByRole("row", { name: /STA-00031/ }));
    expect(libre.getByText("10/12/2026 06:00")).toBeVisible();
    expect(libre.getByText("Pereira → Bogotá")).toBeVisible();
    expect(libre.getByText("0 / 150")).toBeVisible();
    expect(libre.getByText("Sin ventas")).toBeVisible();
    expect(within(fila("STA-00051")).getByText("3 / 150")).toBeVisible();
    expect(within(fila("STA-00051")).getByText("2 reservas activas")).toBeVisible();
    expect(within(fila("STA-00088")).getByText("99 tiquetes vendidos")).toBeVisible();
    expect(consultas()[0].searchParams.get("estado")).toBe("programado");
  });

  it("un vuelo con reservas o compras no se edita y dice el motivo", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    renderRutas(rutas, "/admin/vuelos");
    await screen.findByRole("row", { name: /STA-00031/ });

    expect(within(fila("STA-00031")).getByRole("link", { name: /Editar/ })).toHaveAttribute(
      "href",
      "/admin/vuelos/31/editar",
    );
    for (const codigo of ["STA-00051", "STA-00088"]) {
      expect(within(fila(codigo)).getByRole("button", { name: /Editar/ })).toBeDisabled();
    }
    expect(within(fila("STA-00051")).getByText("Tiene 2 reservas activas.")).toBeVisible();
    expect(within(fila("STA-00088")).getByText("Tiene compras de tiquetes.")).toBeVisible();
  });

  it("con tiquetes vendidos no se cancela: queda «Fuerza mayor»", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    renderRutas(rutas, "/admin/vuelos");
    await screen.findByRole("row", { name: /STA-00031/ });

    const vendido = within(fila("STA-00088"));
    expect(vendido.queryByRole("button", { name: /^Cancelar/ })).not.toBeInTheDocument();
    expect(vendido.getByRole("button", { name: /Fuerza mayor/ })).toBeDisabled();
    expect(within(fila("STA-00031")).getByRole("button", { name: /^Cancelar/ })).toBeEnabled();
  });

  it("«Promoción» abre la promoción de ese vuelo", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    renderRutas(rutas, "/admin/vuelos");
    await screen.findByRole("row", { name: /STA-00031/ });

    // Aun con reservas o compras: la promoción sirve justamente para vender más.
    for (const [codigo, id] of [
      ["STA-00031", 31],
      ["STA-00051", 51],
      ["STA-00088", 88],
    ] as const) {
      expect(within(fila(codigo)).getByRole("link", { name: /Promoción/ })).toHaveAttribute(
        "href",
        `/admin/vuelos/${id}/promocion`,
      );
    }
  });

  it("«Programar vuelo» lleva al formulario", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    renderRutas(rutas, "/admin/vuelos");

    await userEvent.setup().click(await screen.findByRole("link", { name: "Programar vuelo" }));
    expect(await screen.findByText("Formulario de programar vuelo")).toBeVisible();
  });

  it("filtra por texto y por fechas, y lo deja en la dirección", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    const { router } = renderRutas(rutas, "/admin/vuelos");
    const user = userEvent.setup();
    await screen.findByRole("row", { name: /STA-00031/ });

    await user.type(screen.getByLabelText("Buscar por código o ciudad"), "Pereira");
    await user.type(screen.getByLabelText("Salida desde"), "2026-12-01");
    await user.type(screen.getByLabelText("Salida hasta"), "2026-12-31");

    await waitFor(() => {
      const ultima = consultas().at(-1)!;
      expect(ultima.searchParams.get("q")).toBe("Pereira");
      expect(ultima.searchParams.get("desde")).toBe("2026-12-01");
      expect(ultima.searchParams.get("hasta")).toBe("2026-12-31");
    });
    expect(router.state.location.search).toContain("q=Pereira");
    // Una sola petición por el texto: no una por tecla.
    expect(consultas().filter((u) => u.searchParams.get("q")?.length).length).toBeLessThan(4);
  });

  it("«Limpiar filtros» los quita", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    const { router } = renderRutas(rutas, "/admin/vuelos?q=Pereira&desde=2026-12-01");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Limpiar filtros" }));

    expect(router.state.location.search).toBe("");
    expect(screen.getByLabelText("Buscar por código o ciudad")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Limpiar filtros" })).not.toBeInTheDocument();
  });

  it("un periodo con fin anterior al inicio se corrige antes de consultar", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
    renderRutas(rutas, "/admin/vuelos?desde=2026-12-31&hasta=2026-12-01");

    expect(
      await screen.findByText("La fecha final no puede ser anterior a la inicial."),
    ).toBeVisible();
    expect(consultas()).toHaveLength(0);
  });

  it("sin resultados lo dice según haya filtros o no", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina([]) });
    renderRutas(rutas, "/admin/vuelos?q=Mitú");
    expect(await screen.findByText("No hay vuelos programados con estos filtros.")).toBeVisible();
  });

  it("sin vuelos ni filtros invita a programar", async () => {
    responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina([]) });
    renderRutas(rutas, "/admin/vuelos");
    expect(await screen.findByText("Todavía no hay vuelos programados.")).toBeVisible();
  });

  it("pagina el listado", async () => {
    responderApi({
      [SESION]: sesionDe(ADMIN),
      [LISTA]: (url) => pagina(VUELOS, 25, Number(url.searchParams.get("pagina") ?? 1)),
    });
    const { router } = renderRutas(rutas, "/admin/vuelos");
    await screen.findByRole("row", { name: /STA-00031/ });

    await userEvent.setup().click(screen.getByRole("button", { name: "Página 2" }));

    await waitFor(() => expect(consultas().at(-1)!.searchParams.get("pagina")).toBe("2"));
    expect(router.state.location.search).toBe("?pagina=2");
  });

  describe("cancelar (HU-16)", () => {
    it("confirma con las reservas activas que se anularán y cancela el vuelo", async () => {
      let cancelado = false;
      responderApi({
        [SESION]: sesionDe(ADMIN),
        [LISTA]: () => pagina(cancelado ? [vueloAdmin(), conTiquetes()] : VUELOS),
        [CANCELAR_51]: () => {
          cancelado = true;
          return {
            status: 200,
            body: { vuelo: conReservas({ estado: "cancelado" }), reservas_anuladas: 2 },
          };
        },
      });
      renderRutas(rutas, "/admin/vuelos");
      const user = userEvent.setup();
      await screen.findByRole("row", { name: /STA-00051/ });

      await user.click(within(fila("STA-00051")).getByRole("button", { name: /^Cancelar/ }));

      const dialogo = within(await screen.findByRole("dialog"));
      expect(dialogo.getByText("¿Cancelar el vuelo STA-00051?")).toBeVisible();
      expect(dialogo.getByText(/Pereira → Medellín, 10\/12\/2026 07:40\./)).toBeVisible();
      expect(dialogo.getByText("2 reservas activas")).toBeVisible();
      expect(dialogo.getByText(/Se anularán, sus sillas se liberarán/)).toBeVisible();

      await user.click(dialogo.getByRole("button", { name: "Cancelar vuelo" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      await waitFor(() =>
        expect(screen.queryByRole("row", { name: /STA-00051/ })).not.toBeInTheDocument(),
      );
      expect(screen.getByRole("row", { name: /STA-00031/ })).toBeVisible();
    });

    it("«Volver» cierra sin cancelar", async () => {
      responderApi({ [SESION]: sesionDe(ADMIN), [LISTA]: pagina(VUELOS) });
      renderRutas(rutas, "/admin/vuelos");
      const user = userEvent.setup();
      await screen.findByRole("row", { name: /STA-00031/ });

      await user.click(within(fila("STA-00031")).getByRole("button", { name: /^Cancelar/ }));
      const dialogo = within(await screen.findByRole("dialog"));
      expect(dialogo.getByText("No tiene reservas activas.")).toBeVisible();
      await user.click(dialogo.getByRole("button", { name: "Volver" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      const cancelaciones = vi
        .mocked(fetch)
        .mock.calls.filter(([r]) => (r as Request).url.includes("/cancelar"));
      expect(cancelaciones).toHaveLength(0);
    });

    it("si el servidor lo rechaza, explica el motivo en el diálogo", async () => {
      responderApi({
        [SESION]: sesionDe(ADMIN),
        [LISTA]: pagina(VUELOS),
        [CANCELAR_51]: {
          status: 409,
          body: {
            error: {
              codigo: "vuelo_con_tiquetes",
              mensaje: "El vuelo tiene tiquetes vendidos: requiere cancelación por fuerza mayor.",
            },
          },
        },
      });
      renderRutas(rutas, "/admin/vuelos");
      const user = userEvent.setup();
      await screen.findByRole("row", { name: /STA-00051/ });

      await user.click(within(fila("STA-00051")).getByRole("button", { name: /^Cancelar/ }));
      await user.click(await screen.findByRole("button", { name: "Cancelar vuelo" }));

      expect(await screen.findByText(/requiere cancelación por fuerza mayor/)).toBeVisible();
      expect(screen.getByRole("dialog")).toBeVisible();
    });
  });
});
