import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecargarMonederoPage } from "@/pages/recargar-monedero";
import { responderApi } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  { path: "/monedero/recargar", element: <RecargarMonederoPage /> },
  { path: "/monedero/tarjetas/nueva", element: <p>Registrar tarjeta</p> },
  { path: "/monedero", element: <p>Monedero</p> },
  { path: "/compra/pago/:compraId", element: <p>Pago de la compra</p> },
  { path: "/mis-viajes", element: <p>Mis viajes</p> },
];

const GET_TARJETAS = "GET /api/v1/monedero/tarjetas";
const CREAR = "POST /api/v1/monedero/recargas";

const TARJETAS = [
  {
    id: 21,
    tipo: "credito",
    franquicia: "visa",
    titular: "LAURA GOMEZ RIOS",
    numero_enmascarado: "**** 4242",
    vencimiento: "08/28",
    vencida: false,
    creada_en: "2026-09-29T15:05:00Z",
  },
  {
    id: 22,
    tipo: "debito",
    franquicia: "mastercard",
    titular: "LAURA GOMEZ RIOS",
    numero_enmascarado: "**** 5100",
    vencimiento: "01/27",
    vencida: false,
    creada_en: "2026-09-18T17:35:00Z",
  },
  {
    id: 23,
    tipo: "credito",
    franquicia: "visa",
    titular: "LAURA GOMEZ RIOS",
    numero_enmascarado: "**** 1111",
    vencimiento: "05/26",
    vencida: true,
    creada_en: "2025-06-01T12:00:00Z",
  },
];

const MOVIMIENTO = {
  id: 38,
  tipo: "recarga",
  valor: 500000,
  saldo_resultante: 1500000,
  referencia: "**** 4242",
  creado_en: "2026-11-16T12:00:00Z",
};

const servidor = (extra: Record<string, unknown> = {}) =>
  responderApi({
    [GET_TARJETAS]: { status: 200, body: TARJETAS },
    [CREAR]: { status: 201, body: MOVIMIENTO },
    ...extra,
  } as Parameters<typeof responderApi>[0]);

const peticiones = (metodo: string, ruta: string) =>
  vi
    .mocked(fetch)
    .mock.calls.map(([entrada]) => entrada as Request)
    .filter((peticion) => peticion.method === metodo && new URL(peticion.url).pathname === ruta);

async function recargar(valor = "500000") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Valor"), valor);
  await user.click(screen.getByRole("button", { name: /^Recargar/ }));
  return user;
}

const RECARGA_DESDE_COMPRA =
  "/monedero/recargar?faltante=300000&codigo=K7Q2PX&volver=%2Fcompra%2Fpago%2F901%3Fseleccion%3D71";
const RECARGA_DESDE_RESERVA =
  "/monedero/recargar?faltante=500000&codigo=H4N8WQ&volver=%2Fmis-viajes%3Ftipo%3Dreserva%26pagar%3D41";

describe("Recargar monedero (HU-30)", () => {
  // HU-30, RF-47: una recarga de $ 500.000 aumenta el saldo exactamente en $ 500.000.
  it("una recarga de $ 500.000 deja el saldo en $ 1.500.000 y registra la referencia de la tarjeta", async () => {
    servidor();
    renderRutas(rutas, "/monedero/recargar");

    await recargar();

    expect(await screen.findByText("Recarga aprobada")).toBeVisible();
    expect(screen.getByText("$ 1.500.000")).toBeVisible();
    expect(screen.getByText("Tu saldo aumentó exactamente en $ 500.000.")).toBeVisible();
    expect(screen.getByText(/\*\*\*\* 4242/)).toBeVisible();

    const [peticion] = peticiones("POST", "/api/v1/monedero/recargas");
    expect(await peticion.json()).toEqual({ tarjeta_id: 21, valor: 500000 });
  });

  // HU-30: el valor debe ser un entero mayor que 0.
  it.each([
    ["0", "Debe ser mayor que 0."],
    ["", "Escribe el valor de la recarga."],
  ])("rechaza el valor «%s» sin llamar a la API", async (valor, mensaje) => {
    servidor();
    renderRutas(rutas, "/monedero/recargar");

    const user = userEvent.setup();
    await screen.findByLabelText("Valor");
    if (valor) await user.type(screen.getByLabelText("Valor"), valor);
    await user.click(screen.getByRole("button", { name: "Recargar" }));

    expect(await screen.findByText(mensaje)).toBeVisible();
    expect(peticiones("POST", "/api/v1/monedero/recargas")).toHaveLength(0);
  });

  // HU-30: recargar con una tarjeta vencida muestra el error del servidor junto a la tarjeta.
  it("muestra junto a la tarjeta el error tarjeta_vencida del servidor", async () => {
    servidor({
      [CREAR]: {
        status: 422,
        body: {
          error: {
            codigo: "tarjeta_vencida",
            mensaje: "La tarjeta está vencida.",
            campos: { tarjeta_id: "La tarjeta está vencida. Elige otra o registra una nueva." },
          },
        },
      },
    });
    renderRutas(rutas, "/monedero/recargar");

    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Desde la tarjeta"), "23");
    await user.type(screen.getByLabelText("Valor"), "500000");
    await user.click(screen.getByRole("button", { name: /^Recargar/ }));

    expect(
      await screen.findByText("La tarjeta está vencida. Elige otra o registra una nueva."),
    ).toBeVisible();
    expect(screen.getByLabelText("Desde la tarjeta")).toHaveAttribute("aria-invalid", "true");
    const [peticion] = peticiones("POST", "/api/v1/monedero/recargas");
    expect(await peticion.json()).toEqual({ tarjeta_id: 23, valor: 500000 });
  });

  // HU-30: sin tarjetas registradas se pide registrar una y se vuelve a la recarga.
  it("sin tarjetas pide registrar una y vuelve a la recarga", async () => {
    servidor({ [GET_TARJETAS]: { status: 200, body: [] } });
    renderRutas(rutas, "/monedero/recargar");

    expect(
      await screen.findByText(
        "No tienes tarjetas registradas. Registra una para recargar tu monedero.",
      ),
    ).toBeVisible();

    const enlace = screen.getByRole("link", { name: "Registrar tarjeta" });
    const destino = new URL(enlace.getAttribute("href") ?? "", window.location.origin);
    expect(destino.pathname).toBe("/monedero/tarjetas/nueva");
    expect(destino.searchParams.get("volver")).toBe("/monedero/recargar");
  });

  it("sin tarjetas y con faltante, el registro vuelve a la recarga con sus parámetros", async () => {
    servidor({ [GET_TARJETAS]: { status: 200, body: [] } });
    renderRutas(rutas, RECARGA_DESDE_COMPRA);

    expect(
      await screen.findByText(
        "Vienes de tu compra K7Q2PX: te faltan $ 300.000. Al recargar volvemos al pago.",
      ),
    ).toBeVisible();

    const enlace = screen.getByRole("link", { name: "Registrar tarjeta" });
    const destino = new URL(enlace.getAttribute("href") ?? "", window.location.origin);
    expect(destino.searchParams.get("volver")).toBe(RECARGA_DESDE_COMPRA);
  });

  // HU-30: desde una compra con saldo insuficiente propone el faltante y vuelve al pago.
  it("desde una compra propone el faltante y vuelve a la confirmación del pago", async () => {
    servidor();
    const { router } = renderRutas(rutas, RECARGA_DESDE_COMPRA);

    expect(
      await screen.findByText(
        "Vienes de tu compra K7Q2PX: te faltan $ 300.000. Al recargar volvemos al pago.",
      ),
    ).toBeVisible();
    expect(screen.getByLabelText("Valor")).toHaveValue("$ 300.000");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Recargar $ 300.000" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/compra/pago/901"));
    expect(router.state.location.search).toBe("?seleccion=71");
    const [peticion] = peticiones("POST", "/api/v1/monedero/recargas");
    expect(await peticion.json()).toEqual({ tarjeta_id: 21, valor: 300000 });
  });

  it("desde una reserva propone el faltante y vuelve a Mis viajes", async () => {
    servidor();
    const { router } = renderRutas(rutas, RECARGA_DESDE_RESERVA);

    expect(
      await screen.findByText(
        "Vienes de tu reserva H4N8WQ: te faltan $ 500.000. Al recargar volvemos a Mis viajes.",
      ),
    ).toBeVisible();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Recargar $ 500.000" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/mis-viajes"));
    expect(router.state.location.search).toBe("?tipo=reserva&pagar=41");
  });

  it("ignora un `volver` externo y vuelve al monedero", async () => {
    servidor();
    const { router } = renderRutas(
      rutas,
      "/monedero/recargar?faltante=100000&codigo=ABC123&volver=https%3A%2F%2Fevil.example%2Frobar",
    );

    expect(
      await screen.findByText(
        "Vienes de ABC123: te faltan $ 100.000. Al recargar volvemos a donde estabas.",
      ),
    ).toBeVisible();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Recargar $ 100.000" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/monedero"));
  });

  it("muestra el 404 no_encontrado del servidor y refresca las tarjetas", async () => {
    servidor({
      [CREAR]: {
        status: 404,
        body: { error: { codigo: "no_encontrado", mensaje: "La tarjeta no existe." } },
      },
    });
    renderRutas(rutas, "/monedero/recargar");

    await recargar();

    expect(await screen.findByText("La tarjeta no existe.")).toBeVisible();
    await waitFor(() =>
      expect(peticiones("GET", "/api/v1/monedero/tarjetas").length).toBeGreaterThanOrEqual(2),
    );
  });

  it("muestra un aviso cuando el servidor falla sin marcar un campo", async () => {
    servidor({
      [CREAR]: {
        status: 500,
        body: { error: { codigo: "error_interno", mensaje: "Ocurrió un error inesperado." } },
      },
    });
    renderRutas(rutas, "/monedero/recargar");

    await recargar();

    expect(await screen.findByText("Ocurrió un error inesperado.")).toBeVisible();
  });

  it("ignora un faltante que no es un entero mayor que 0", async () => {
    servidor();
    renderRutas(rutas, "/monedero/recargar?faltante=0");

    expect(await screen.findByLabelText("Valor")).toHaveValue("");
    expect(screen.queryByText(/Vienes de/)).not.toBeInTheDocument();
  });
});
