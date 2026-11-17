import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schemas } from "@/api/client";
import { MonederoPage } from "@/pages/monedero";
import { responderApi } from "@/test/api";
import { renderRutas } from "@/test/render";

type Tarjeta = Schemas["Tarjeta"];
type Movimiento = Schemas["Movimiento"];

const MONEDERO = "GET /api/v1/monedero";
const MOVIMIENTOS = "GET /api/v1/monedero/movimientos";
const TARJETAS = "GET /api/v1/monedero/tarjetas";
const ELIMINAR_21 = "DELETE /api/v1/monedero/tarjetas/21";

const rutas = [
  { path: "/monedero", element: <MonederoPage /> },
  { path: "/monedero/recargar", element: <p>Recargar monedero</p> },
  { path: "/monedero/tarjetas/nueva", element: <p>Registrar tarjeta</p> },
];

const tarjeta = (cambios: Partial<Tarjeta>): Tarjeta => ({
  id: 21,
  tipo: "credito",
  franquicia: "visa",
  titular: "LAURA GOMEZ RIOS",
  numero_enmascarado: "**** 4242",
  vencimiento: "08/28",
  vencida: false,
  creada_en: "2026-09-29T15:05:00Z",
  ...cambios,
});

const VISA = tarjeta({});
const MASTERCARD = tarjeta({
  id: 22,
  tipo: "debito",
  franquicia: "mastercard",
  numero_enmascarado: "**** 5100",
  vencimiento: "01/27",
});
const VENCIDA = tarjeta({
  id: 23,
  numero_enmascarado: "**** 1111",
  vencimiento: "05/26",
  vencida: true,
});

const movimiento = (cambios: Partial<Movimiento>): Movimiento => ({
  id: 1,
  tipo: "recarga",
  valor: 500_000,
  saldo_resultante: 1_000_000,
  referencia: "**** 4242",
  creado_en: "2026-09-29T15:09:00Z",
  ...cambios,
});

/** Del más reciente al más antiguo, como los entrega el servidor. */
const MOVIMIENTOS_DE_LAURA: Movimiento[] = [
  movimiento({
    id: 5,
    tipo: "compra",
    valor: -800_000,
    saldo_resultante: 200_000,
    referencia: "K7Q2PX",
    creado_en: "2026-09-29T15:14:00Z",
  }),
  movimiento({
    id: 4,
    tipo: "recarga",
    valor: 500_000,
    saldo_resultante: 1_000_000,
    creado_en: "2026-09-29T15:09:00Z",
  }),
  movimiento({
    id: 3,
    tipo: "reembolso",
    valor: 185_000,
    saldo_resultante: 500_000,
    referencia: "B3M9TA",
    creado_en: "2026-09-21T23:30:00Z",
  }),
];

const pagina = (items: Movimiento[], extra = {}) => ({
  items,
  total: items.length,
  pagina: 1,
  por_pagina: 20,
  ...extra,
});
const ok = (body: unknown) => ({ status: 200, body });

const base = (extra: Record<string, unknown> = {}) => ({
  [MONEDERO]: ok({ saldo: 200_000 }),
  [MOVIMIENTOS]: ok(pagina(MOVIMIENTOS_DE_LAURA)),
  [TARJETAS]: ok([VISA, MASTERCARD]),
  ...extra,
});

const consultas = () =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => new URL((r as Request).url))
    .filter((u) => u.pathname === "/api/v1/monedero/movimientos");
const ultima = () => consultas().at(-1)!.searchParams;
const eliminaciones = () =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => r.method === "DELETE");

const abrir = (url = "/monedero") => renderRutas(rutas, url);
const tabla = async () =>
  within(await screen.findByRole("table", { name: "Movimientos del monedero" }));
const panelTarjetas = async () =>
  within((await screen.findByText("Tus tarjetas")).closest("section")!);

describe("S22 · Monedero (HU-29, HU-31)", () => {
  it("HU-31: muestra el saldo y los movimientos del más reciente al más antiguo", async () => {
    responderApi(base());
    abrir();

    expect(await screen.findByText("$ 200.000", { selector: ".display-xl" })).toBeVisible();
    const t = await tabla();
    const filas = t.getAllByRole("row").slice(1);
    expect(filas).toHaveLength(3);
    const primera = within(filas[0]);
    expect(primera.getByText("29/09/2026 10:14")).toBeVisible(); // hora de Colombia
    expect(primera.getByText("Compra")).toBeVisible();
    expect(primera.getByText("K7Q2PX")).toBeVisible();
    expect(primera.getByText("− $ 800.000")).toBeVisible();
    expect(primera.getByText("$ 200.000")).toBeVisible();
    const segunda = within(filas[1]);
    expect(segunda.getByText("Recarga")).toBeVisible();
    expect(segunda.getByText("**** 4242")).toBeVisible();
    expect(segunda.getByText("+ $ 500.000")).toBeVisible();
    expect(segunda.getByText("$ 1.000.000")).toBeVisible();
    expect(within(filas[2]).getByText("B3M9TA")).toBeVisible();
    expect(screen.getByText(/El saldo es siempre la suma de tus movimientos/)).toBeVisible();
  });

  it("HU-31: filtrar por «Recargas» pide solo las recargas", async () => {
    responderApi(
      base({
        [MOVIMIENTOS]: (url: URL) =>
          ok(
            pagina(
              url.searchParams.get("tipo") === "recarga"
                ? MOVIMIENTOS_DE_LAURA.filter((m) => m.tipo === "recarga")
                : MOVIMIENTOS_DE_LAURA,
            ),
          ),
      }),
    );
    abrir();
    await tabla();

    await userEvent.click(screen.getByRole("button", { name: "Recargas" }));

    await waitFor(() => expect(ultima().get("tipo")).toBe("recarga"));
    const t = await tabla();
    await waitFor(() => expect(t.getAllByRole("row")).toHaveLength(2));
    expect(t.queryByText("K7Q2PX")).toBeNull();
    expect(screen.getByRole("button", { name: "Recargas", pressed: true })).toBeVisible();
  });

  it("HU-31: también se filtra por fecha, con el primer y el último día", async () => {
    responderApi(base());
    abrir();
    await tabla();

    await userEvent.type(screen.getByLabelText("Desde"), "2026-09-21");
    await userEvent.type(screen.getByLabelText("Hasta"), "2026-09-29");

    await waitFor(() => expect(ultima().get("hasta")).toBe("2026-09-29"));
    expect(ultima().get("desde")).toBe("2026-09-21");
  });

  it("una fecha final anterior a la inicial se marca junto al campo y no se envía", async () => {
    responderApi(base());
    abrir("/monedero?desde=2026-09-29&hasta=2026-09-21");

    expect(
      await screen.findByText("La fecha final no puede ser anterior a la inicial."),
    ).toBeVisible();
    expect(screen.getByLabelText("Hasta")).toHaveAttribute("aria-invalid", "true");
    expect(consultas()).toHaveLength(0);
  });

  it("el rango_invalido del servidor también se muestra junto a «Hasta»", async () => {
    responderApi(
      base({
        [MOVIMIENTOS]: {
          status: 422,
          body: {
            error: {
              codigo: "rango_invalido",
              mensaje: "Revisa los rangos marcados.",
              campos: { hasta: "La fecha final no puede ser anterior a la inicial." },
            },
          },
        },
      }),
    );
    abrir("/monedero?desde=2026-09-21&hasta=2026-09-29");

    expect(
      await screen.findByText("La fecha final no puede ser anterior a la inicial."),
    ).toBeVisible();
  });

  it("HU-31: un cliente sin movimientos ve saldo $ 0 y la opción de recargar", async () => {
    responderApi(
      base({ [MONEDERO]: ok({ saldo: 0 }), [MOVIMIENTOS]: ok(pagina([])), [TARJETAS]: ok([]) }),
    );
    abrir();

    expect(await screen.findByText("$ 0", { selector: ".display-xl" })).toBeVisible();
    expect(await screen.findByText(/Todavía no tienes movimientos/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Recargar monedero" })).toHaveAttribute(
      "href",
      "/monedero/recargar",
    );
    expect(screen.getByRole("link", { name: "Recargar" })).toHaveAttribute(
      "href",
      "/monedero/recargar",
    );
    expect(screen.getByText(/No tienes tarjetas registradas/)).toBeVisible();
  });

  it("con filtros y sin resultados invita a quitarlos", async () => {
    responderApi(base({ [MOVIMIENTOS]: ok(pagina([])) }));
    abrir("/monedero?tipo=reembolso");

    expect(await screen.findByText("No hay movimientos con estos filtros.")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Quitar filtros" }));
    await waitFor(() => expect(ultima().get("tipo")).toBeNull());
  });

  it("las tarjetas se muestran enmascaradas, con su franquicia y su vencimiento", async () => {
    responderApi(base({ [TARJETAS]: ok([VISA, MASTERCARD, VENCIDA]) }));
    abrir();

    const panel = await panelTarjetas();
    expect(await panel.findByText("**** 4242")).toBeVisible();
    expect(panel.getByText("Crédito, Visa, Vence 08/28")).toBeVisible();
    expect(panel.getByText("**** 5100")).toBeVisible();
    expect(panel.getByText("Débito, Mastercard, Vence 01/27")).toBeVisible();
    expect(panel.getByText("**** 1111")).toBeVisible();
    // La vencida se marca con palabras y también se puede eliminar.
    expect(panel.getByText("Vencida")).toBeVisible();
    expect(panel.getByRole("button", { name: /Eliminar la tarjeta \*\*\*\* 1111/ })).toBeVisible();
    expect(panel.getByRole("link", { name: "Registrar tarjeta" })).toHaveAttribute(
      "href",
      "/monedero/tarjetas/nueva",
    );
  });

  it("HU-29: eliminar una tarjeta pide confirmación, la quita de la lista y sus recargas conservan la referencia", async () => {
    let tarjetas = [VISA, MASTERCARD];
    responderApi(
      base({
        [TARJETAS]: () => ok(tarjetas),
        [ELIMINAR_21]: () => {
          tarjetas = [MASTERCARD];
          return { status: 204 };
        },
      }),
    );
    abrir();
    const panel = await panelTarjetas();

    await userEvent.click(
      await panel.findByRole("button", { name: /Eliminar la tarjeta \*\*\*\* 4242/ }),
    );
    const dialogo = within(
      await screen.findByRole("dialog", { name: "¿Eliminar la tarjeta **** 4242?" }),
    );
    expect(
      dialogo.getByText(/Las recargas que ya hiciste con ella siguen en tus movimientos/),
    ).toBeVisible();
    await userEvent.click(dialogo.getByRole("button", { name: "Eliminar tarjeta" }));

    await waitFor(() => expect(panel.queryByText("**** 4242")).toBeNull());
    expect(panel.getByText("**** 5100")).toBeVisible();
    expect(eliminaciones()).toHaveLength(1);
    // La recarga hecha con esa tarjeta sigue mostrando su referencia en los movimientos.
    expect((await tabla()).getByText("**** 4242")).toBeVisible();
  });

  it("«Volver» en la confirmación no elimina nada", async () => {
    responderApi(base());
    abrir();
    const panel = await panelTarjetas();

    await userEvent.click(
      await panel.findByRole("button", { name: /Eliminar la tarjeta \*\*\*\* 4242/ }),
    );
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Volver" }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(eliminaciones()).toHaveLength(0);
    expect(panel.getByText("**** 4242")).toBeVisible();
  });

  it("si la tarjeta ya se había eliminado (404), lo dice y la lista se actualiza", async () => {
    let tarjetas = [VISA, MASTERCARD];
    responderApi(
      base({
        [TARJETAS]: () => ok(tarjetas),
        [ELIMINAR_21]: () => {
          tarjetas = [MASTERCARD];
          return {
            status: 404,
            body: { error: { codigo: "no_encontrado", mensaje: "La tarjeta no existe." } },
          };
        },
      }),
    );
    abrir();
    const panel = await panelTarjetas();

    await userEvent.click(
      await panel.findByRole("button", { name: /Eliminar la tarjeta \*\*\*\* 4242/ }),
    );
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Eliminar tarjeta" }),
    );

    expect(await screen.findByText("La tarjeta no existe.")).toBeVisible();
    await waitFor(() => expect(panel.queryByText("**** 4242")).toBeNull());
  });

  it("pagina los movimientos de 20 en 20", async () => {
    responderApi(
      base({
        [MOVIMIENTOS]: (url: URL) =>
          ok(
            pagina(MOVIMIENTOS_DE_LAURA, {
              total: 45,
              pagina: Number(url.searchParams.get("pagina")),
            }),
          ),
      }),
    );
    abrir();
    await tabla();

    await userEvent.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => expect(ultima().get("pagina")).toBe("2"));
    expect(ultima().get("por_pagina")).toBe("20");
  });
});
