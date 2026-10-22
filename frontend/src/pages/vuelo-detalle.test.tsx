import { screen, within } from "@testing-library/react";
import { VueloDetallePage } from "@/pages/vuelo-detalle";
import { responderApi, SIN_SESION } from "@/test/api";
import { vueloDetalle } from "@/test/noticias";
import { renderRutas } from "@/test/render";

const rutas = [{ path: "/vuelos/:vueloId", element: <VueloDetallePage /> }];

const dePagina = (v: ReturnType<typeof vueloDetalle>) => ({
  "GET /api/v1/auth/me": SIN_SESION,
  [`GET /api/v1/vuelos/${v.id}`]: { status: 200, body: v },
});

describe("Detalle público del vuelo (HU-19)", () => {
  // IU-05, RF-15: hora local de cada ciudad con su desfase.
  it("muestra la salida y la llegada en la hora local de cada ciudad con su desfase", async () => {
    responderApi(dePagina(vueloDetalle())); // 10/12 22:00 Bogotá → 11/12 14:00 Madrid (UTC+1)
    renderRutas(rutas, "/vuelos/88");

    const pasabordo = await screen.findByRole("article", {
      name: "Vuelo STA-00088 Bogotá a Madrid",
    });
    expect(within(pasabordo).getByText("22:00")).toBeVisible();
    expect(within(pasabordo).getByText("Bogotá · UTC-5")).toBeVisible();
    expect(within(pasabordo).getByText("14:00 · 11/12/2026")).toBeVisible();
    expect(within(pasabordo).getByText("Madrid · UTC+1")).toBeVisible();
    expect(within(pasabordo).getByText("Salida 10/12/2026")).toBeVisible();
    expect(within(pasabordo).getByText("10 h")).toBeVisible();
  });

  it("en horario de verano de Madrid el desfase es UTC+2", async () => {
    responderApi(
      dePagina(vueloDetalle({ salida: "2026-07-11T03:00:00Z", llegada: "2026-07-11T13:00:00Z" })),
    );
    renderRutas(rutas, "/vuelos/88");

    // 10/07 22:00 en Bogotá, y llega 15:00 en Madrid (UTC+2) del 11/07.
    expect(await screen.findByText("Madrid · UTC+2")).toBeVisible();
    expect(screen.getByText("15:00 · 11/07/2026")).toBeVisible();
  });

  it("muestra el precio de cada clase y las sillas libres", async () => {
    responderApi(dePagina(vueloDetalle()));
    renderRutas(rutas, "/vuelos/88");

    const fila = async (clase: string) => (await screen.findByText(clase)).closest("tr")!;
    expect(within(await fila("Económica")).getByText("$ 2.450.000")).toBeVisible();
    expect(within(await fila("Económica")).getByText("120")).toBeVisible();
    expect(within(await fila("Primera")).getByText("$ 6.900.000")).toBeVisible();
  });

  // RF-24: el precio vigente incluye la promoción; la vencida no se muestra como vigente.
  it("muestra el precio con descuento solo si la promoción está vigente", async () => {
    const promo = {
      id: 1,
      porcentaje: 40,
      clases: ["economica" as const],
      inicio: "2026-10-15T15:00:00Z",
      fin: "2026-12-01T17:00:00Z",
    };
    responderApi(
      dePagina(
        vueloDetalle({
          economica: {
            precio_base: 2450000,
            precio_vigente: 1470000,
            promocion: { ...promo, estado: "vigente" },
            disponibles: 120,
            agotada: false,
          },
        }),
      ),
    );
    renderRutas(rutas, "/vuelos/88");

    const fila = (await screen.findByText("Económica")).closest("tr")!;
    expect(within(fila).getByText("Promoción −40 %")).toBeVisible();
    expect(within(fila).getByText("$ 1.470.000")).toBeVisible();
    expect(within(fila).getByText(/\$ 2\.450\.000/)).toBeVisible();
    expect(within(fila).getByText("Hasta el 01/12/2026 12:00 hora de Colombia")).toBeVisible();
  });

  it("una promoción vencida no se muestra como vigente", async () => {
    const promo = {
      id: 1,
      porcentaje: 40,
      clases: ["economica" as const],
      inicio: "2026-10-01T15:00:00Z",
      fin: "2026-10-10T17:00:00Z",
    };
    responderApi(
      dePagina(
        vueloDetalle({
          economica: { ...vueloDetalle().economica, promocion: { ...promo, estado: "vencida" } },
        }),
      ),
    );
    renderRutas(rutas, "/vuelos/88");

    const fila = (await screen.findByText("Económica")).closest("tr")!;
    expect(within(fila).queryByText(/Promoción/)).not.toBeInTheDocument();
    expect(within(fila).getByText("$ 2.450.000")).toBeVisible();
  });

  it("marca la clase agotada con palabra y, si ambas lo están, el vuelo entero", async () => {
    const agotada = { ...vueloDetalle().economica, disponibles: 0, agotada: true };
    responderApi(dePagina(vueloDetalle({ economica: agotada, primera: agotada })));
    renderRutas(rutas, "/vuelos/88");

    const pasabordo = await screen.findByRole("article");
    expect(within(pasabordo).getAllByText("Agotado").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Agotada")).toHaveLength(2);
  });

  // HU-19: el detalle avisa si el vuelo ya no está programado.
  it.each([
    ["cancelado", "Este vuelo fue cancelado y no está disponible."],
    ["realizado", "Este vuelo ya se realizó y no está disponible para la venta."],
  ] as const)("avisa si el vuelo está %s", async (estado, aviso) => {
    responderApi(dePagina(vueloDetalle({ estado })));
    renderRutas(rutas, "/vuelos/88");

    expect(await screen.findByRole("alert")).toHaveTextContent(aviso);
  });

  it("un vuelo programado no muestra ningún aviso de estado", async () => {
    responderApi(dePagina(vueloDetalle()));
    renderRutas(rutas, "/vuelos/88");

    await screen.findByRole("article");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("un vuelo que no existe lo dice y vuelve a las noticias", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/vuelos/999": {
        status: 404,
        body: { error: { codigo: "no_encontrado", mensaje: "El vuelo no existe." } },
      },
    });
    renderRutas(rutas, "/vuelos/999");

    expect(await screen.findByRole("alert")).toHaveTextContent("No encontramos este vuelo.");
    expect(screen.getByRole("link", { name: "Volver a las noticias" })).toHaveAttribute(
      "href",
      "/noticias",
    );
  });

  it("un identificador que no es un número no consulta al servidor", async () => {
    responderApi({ "GET /api/v1/auth/me": SIN_SESION });
    renderRutas(rutas, "/vuelos/abc");

    expect(await screen.findByRole("heading", { name: "Página no encontrada" })).toBeVisible();
    const llamadas = vi.mocked(fetch).mock.calls.map(([r]) => new URL((r as Request).url).pathname);
    expect(llamadas.some((p) => p.startsWith("/api/v1/vuelos"))).toBe(false);
  });
});
