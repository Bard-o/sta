import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PaginaBusqueda, VueloBusqueda } from "@/pages/buscar/api";
import { BuscarIdaYRegresoPage } from "@/pages/buscar-ida-y-regreso";
import { CLIENTE, responderApi, SIN_SESION, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";
import { ciudad, PEI } from "@/test/vuelos";

const SESION = "GET /api/v1/auth/me";
const BUSCAR = "GET /api/v1/busqueda/vuelos";
const REGRESOS = "GET /api/v1/busqueda/regresos";
const CIUDADES = "GET /api/v1/ciudades";
const AGREGAR = "POST /api/v1/carrito/selecciones";

const rutas = [
  { path: "/buscar/ida-y-regreso", element: <BuscarIdaYRegresoPage /> },
  { path: "/login", element: <p>Inicio de sesión</p> },
  { path: "/carrito", element: <p>Tu carrito</p> },
];

const JFK = ciudad("JFK", "Nueva York", "internacional", "America/New_York");
const CTG = ciudad("CTG", "Cartagena");
const resumen = (c: ReturnType<typeof ciudad>) => ({
  codigo: c.codigo,
  nombre: c.nombre,
  zona_horaria: c.zona_horaria,
});

const clase = (precio: number, disponibles = 20) => ({
  precio_base: precio,
  precio_vigente: precio,
  disponibles,
  agotada: disponibles === 0,
  promocion: null,
});

/** Pereira → Nueva York, 15/04/2027: sale 08:00 de Pereira (13:00Z) y llega 14:30 de Nueva York
 *  (18:30Z). */
const IDA_101: VueloBusqueda = {
  id: 101,
  codigo: "STA-00101",
  tipo: "internacional",
  origen: resumen(PEI),
  destino: resumen(JFK),
  salida: "2027-04-15T13:00:00Z",
  llegada: "2027-04-15T18:30:00Z",
  duracion_minutos: 330,
  economica: clase(1_650_000),
  primera: clase(4_100_000),
  agotado: false,
};
const IDA_104: VueloBusqueda = {
  ...IDA_101,
  id: 104,
  codigo: "STA-00104",
  salida: "2027-04-16T04:10:00Z",
  llegada: "2027-04-16T09:40:00Z",
  economica: clase(1_450_000),
  primera: clase(3_650_000),
};
/** Nueva York → Cartagena, 22/04/2027 10:00 de Nueva York. */
const REGRESO_132: VueloBusqueda = {
  id: 132,
  codigo: "STA-00132",
  tipo: "internacional",
  origen: resumen(JFK),
  destino: resumen(CTG),
  salida: "2027-04-22T14:00:00Z",
  llegada: "2027-04-22T18:20:00Z",
  duracion_minutos: 320,
  economica: clase(1_750_000),
  primera: clase(3_900_000),
  agotado: false,
};
/** El 15/04 sale 06:30 de Nueva York (10:30Z), antes de la llegada de la ida. */
const REGRESO_129: VueloBusqueda = {
  ...REGRESO_132,
  id: 129,
  codigo: "STA-00129",
  salida: "2027-04-15T10:30:00Z",
  llegada: "2027-04-15T15:50:00Z",
  economica: clase(1_620_000),
  primera: clase(3_800_000),
};
/** El 15/04 sale 20:00 de Nueva York (00:00Z del 16): sí es regreso. */
const REGRESO_133: VueloBusqueda = {
  ...REGRESO_132,
  id: 133,
  codigo: "STA-00133",
  salida: "2027-04-16T00:00:00Z",
  llegada: "2027-04-16T04:20:00Z",
  economica: clase(1_580_000),
  primera: clase(3_700_000),
};

const pagina = (items: VueloBusqueda[]): PaginaBusqueda => ({
  items,
  total: items.length,
  pagina: 1,
  por_pagina: 20,
});
const ok = (items: VueloBusqueda[]) => ({ status: 200, body: pagina(items) });

/** El mismo endpoint sirve las idas (sale de Pereira) y los vuelos del día de regreso (sale de
 *  Nueva York, para dibujar los que salen antes de la llegada). */
const buscarVuelos =
  (idas: VueloBusqueda[], delDia: VueloBusqueda[] = []) =>
  (url: URL) =>
    ok(url.searchParams.get("origen") === "PEI" ? idas : delDia);

const base = (extra: Record<string, unknown> = {}) => ({
  [SESION]: SIN_SESION,
  [CIUDADES]: { status: 200, body: [PEI, JFK, CTG] },
  ...extra,
});

const BUSQUEDA = "origen=PEI&destino=JFK&regreso=CTG&fecha_ida=2027-04-15&fecha_regreso=2027-04-22";

const llamadas = (ruta: string) =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => new URL(r.url).pathname === ruta);
const ultima = (ruta: string) => new URL(llamadas(ruta).at(-1)!.url).searchParams;

const pase = (codigo: string) => screen.getByRole("article", { name: new RegExp(codigo) });

async function elegir(codigo: string, como: "ida" | "regreso") {
  await userEvent.click(
    within(await screen.findByRole("article", { name: new RegExp(codigo) })).getByRole("button", {
      name: `Elegir ${codigo} como ${como}`,
    }),
  );
}

describe("S15 · Búsqueda de ida y regreso (HU-21, HU-26)", () => {
  it("pide las ciudades y las fechas y lista las idas con la hora local de cada ciudad", async () => {
    responderApi(
      base({ [BUSCAR]: buscarVuelos([IDA_101, IDA_104]), [REGRESOS]: ok([REGRESO_132]) }),
    );
    const { router } = renderRutas(rutas, "/buscar/ida-y-regreso");
    const form = within(screen.getByRole("search", { name: "Buscar ida y regreso" }));

    expect(screen.getByText(/Indica las ciudades y las fechas/)).toBeVisible();
    await form.findAllByRole("option", { name: "Pereira" }); // el catálogo de ciudades llega después
    await userEvent.selectOptions(form.getByLabelText("Ciudad de salida"), "PEI");
    await userEvent.selectOptions(form.getByLabelText("Ciudad de destino"), "JFK");
    await userEvent.selectOptions(form.getByLabelText("Ciudad de regreso"), "CTG");
    await userEvent.type(form.getByLabelText("Fecha de ida"), "2027-04-15");
    await userEvent.type(form.getByLabelText("Fecha de regreso"), "2027-04-22");
    await userEvent.selectOptions(form.getByLabelText("Viajeros"), "2");
    await userEvent.click(form.getByRole("button", { name: "Buscar vuelos" }));

    const ida = within(await screen.findByRole("article", { name: /STA-00101/ }));
    expect(ida.getByText("08:00")).toBeVisible();
    expect(ida.getByText("14:30")).toBeVisible(); // llegada en la hora de Nueva York
    expect(ida.getByText("5 h 30 min, directo")).toBeVisible();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Pereira → Nueva York → Cartagena" }),
    ).toBeVisible();
    expect(screen.getByText(/Ida el 15\/04\/2027 y regreso el 22\/04\/2027/)).toBeVisible();
    expect(router.state.location.search).toContain("viajeros=2");
    const q = ultima("/api/v1/busqueda/vuelos");
    expect(q.get("origen")).toBe("PEI");
    expect(q.get("destino")).toBe("JFK");
    expect(q.get("fecha_desde")).toBe("2027-04-15");
    expect(q.get("fecha_hasta")).toBe("2027-04-15");
  });

  it("HU-21: antes de elegir la ida no se ofrece ningún regreso", async () => {
    responderApi(base({ [BUSCAR]: buscarVuelos([IDA_101]), [REGRESOS]: ok([REGRESO_132]) }));
    renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}`);

    await screen.findByRole("article", { name: /STA-00101/ });

    expect(screen.getByText(/Elige primero tu ida/)).toBeVisible();
    expect(screen.queryByRole("article", { name: /STA-00132/ })).toBeNull();
    expect(llamadas("/api/v1/busqueda/regresos")).toHaveLength(0);
  });

  it("al elegir la ida pide los regresos con ese vuelo, la ciudad de regreso y la fecha", async () => {
    responderApi(
      base({ [BUSCAR]: buscarVuelos([IDA_101, IDA_104]), [REGRESOS]: ok([REGRESO_132]) }),
    );
    renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}`);

    await elegir("STA-00101", "ida");

    expect(await screen.findByRole("article", { name: /STA-00132/ })).toBeVisible();
    const q = ultima("/api/v1/busqueda/regresos");
    expect(q.get("vuelo_ida_id")).toBe("101");
    expect(q.get("destino")).toBe("CTG");
    expect(q.get("fecha")).toBe("2027-04-22");
    expect(within(pase("STA-00101")).getByText("Elegido")).toBeVisible();
  });

  it("HU-21: un regreso que sale antes de la llegada no se ofrece y se muestra deshabilitado con el motivo", async () => {
    responderApi(
      base({
        [BUSCAR]: buscarVuelos([IDA_101], [REGRESO_129, REGRESO_133]),
        [REGRESOS]: ok([REGRESO_133]),
      }),
    );
    renderRutas(
      rutas,
      "/buscar/ida-y-regreso?origen=PEI&destino=JFK&regreso=CTG&fecha_ida=2027-04-15&fecha_regreso=2027-04-15",
    );

    await elegir("STA-00101", "ida");

    const permitido = within(await screen.findByRole("article", { name: /STA-00133/ }));
    expect(permitido.getByRole("button", { name: "Elegir STA-00133 como regreso" })).toBeVisible();
    const antes = within(screen.getByRole("article", { name: /STA-00129/ }));
    expect(antes.getByText(/Sale a las 06:30, antes de tu llegada a Nueva York/)).toBeVisible();
    expect(antes.queryByRole("button", { name: /Elegir/ })).toBeNull();
  });

  it("HU-26: se arma Pereira → Nueva York → Cartagena con una clase por tramo y el total es la suma, sin descuento combinado", async () => {
    responderApi(base({ [BUSCAR]: buscarVuelos([IDA_101]), [REGRESOS]: ok([REGRESO_132]) }));
    renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}&viajeros=2`);

    await elegir("STA-00101", "ida");
    await elegir("STA-00132", "regreso");
    // Ida en primera ($ 4.100.000) y regreso en económica ($ 1.750.000), para 2 viajeros.
    await userEvent.click(
      within(pase("STA-00101")).getByRole("button", { name: /Primera/, pressed: false }),
    );

    const resumen = within(await screen.findByRole("region", { name: "Trayecto completo" }));
    expect(resumen.getByText("Trayecto completo, 2 viajeros")).toBeVisible();
    expect(resumen.getByText(/Ida en primera y regreso en económica/)).toBeVisible();
    expect(resumen.getByText("$ 11.700.000")).toBeVisible();
    expect(
      within(pase("STA-00101")).getByRole("button", { name: /Primera/, pressed: true }),
    ).toBeVisible();
    expect(
      within(pase("STA-00132")).getByRole("button", { name: /Económica/, pressed: true }),
    ).toBeVisible();
  });

  it("agrega el trayecto al carrito como una sola selección de dos tramos, en orden", async () => {
    responderApi(
      base({
        [SESION]: sesionDe(CLIENTE),
        [BUSCAR]: buscarVuelos([IDA_101]),
        [REGRESOS]: ok([REGRESO_132]),
        [AGREGAR]: { status: 201, body: {} },
      }),
    );
    renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}&viajeros=2`);

    await elegir("STA-00101", "ida");
    await elegir("STA-00132", "regreso");
    await userEvent.click(await screen.findByRole("button", { name: "Agregar al carrito" }));

    await waitFor(() => expect(llamadas("/api/v1/carrito/selecciones")).toHaveLength(1));
    expect(await llamadas("/api/v1/carrito/selecciones")[0].clone().json()).toEqual({
      tramos: [
        { vuelo_id: 101, clase: "economica" },
        { vuelo_id: 132, clase: "economica" },
      ],
      viajeros: 2,
    });
  });

  it("un error del carrito (regreso_invalido) se muestra junto al resumen", async () => {
    responderApi(
      base({
        [SESION]: sesionDe(CLIENTE),
        [BUSCAR]: buscarVuelos([IDA_101]),
        [REGRESOS]: ok([REGRESO_132]),
        [AGREGAR]: {
          status: 422,
          body: {
            error: {
              codigo: "regreso_invalido",
              mensaje: "El regreso debe salir de Nueva York después de la llegada de la ida.",
            },
          },
        },
      }),
    );
    renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}`);

    await elegir("STA-00101", "ida");
    await elegir("STA-00132", "regreso");
    await userEvent.click(await screen.findByRole("button", { name: "Agregar al carrito" }));

    expect(
      await screen.findByText(
        "El regreso debe salir de Nueva York después de la llegada de la ida.",
      ),
    ).toBeVisible();
  });

  it("HU-21: una fecha de regreso anterior a la de ida se rechaza junto al campo, sin buscar", async () => {
    responderApi(base({ [BUSCAR]: buscarVuelos([IDA_101]) }));
    renderRutas(rutas, "/buscar/ida-y-regreso");
    const form = within(screen.getByRole("search", { name: "Buscar ida y regreso" }));

    await form.findAllByRole("option", { name: "Pereira" }); // el catálogo de ciudades llega después
    await userEvent.selectOptions(form.getByLabelText("Ciudad de salida"), "PEI");
    await userEvent.selectOptions(form.getByLabelText("Ciudad de destino"), "JFK");
    await userEvent.selectOptions(form.getByLabelText("Ciudad de regreso"), "CTG");
    await userEvent.type(form.getByLabelText("Fecha de ida"), "2027-04-22");
    await userEvent.type(form.getByLabelText("Fecha de regreso"), "2027-04-15");
    await userEvent.click(form.getByRole("button", { name: "Buscar vuelos" }));

    expect(form.getByText("La fecha de regreso no puede ser anterior a la de ida.")).toBeVisible();
    expect(llamadas("/api/v1/busqueda/vuelos")).toHaveLength(0);
  });

  it("el rango_invalido del servidor sobre la fecha se muestra junto al campo de regreso", async () => {
    responderApi(
      base({
        [BUSCAR]: buscarVuelos([IDA_101]),
        [REGRESOS]: {
          status: 422,
          body: {
            error: {
              codigo: "rango_invalido",
              mensaje: "Revisa los rangos marcados.",
              campos: { fecha: "La fecha de regreso no puede ser anterior a la de ida." },
            },
          },
        },
      }),
    );
    renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}`);

    await elegir("STA-00101", "ida");

    const form = within(screen.getByRole("search", { name: "Buscar ida y regreso" }));
    expect(
      await form.findByText("La fecha de regreso no puede ser anterior a la de ida."),
    ).toBeVisible();
  });

  it("HU-21: sin regresos para esa fecha lo dice y al cambiar la fecha o la ciudad se conserva la ida", async () => {
    responderApi(
      base({
        [BUSCAR]: buscarVuelos([IDA_101]),
        [REGRESOS]: (url: URL) =>
          ok(url.searchParams.get("fecha") === "2027-04-22" ? [] : [REGRESO_133]),
      }),
    );
    const { router } = renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}`);

    await elegir("STA-00101", "ida");
    expect(await screen.findByText("No hay regresos para esa fecha")).toBeVisible();
    expect(screen.getByText(/tu ida se conserva/)).toBeVisible();

    const form = within(screen.getByRole("search", { name: "Buscar ida y regreso" }));
    const fecha = form.getByLabelText("Fecha de regreso");
    await userEvent.clear(fecha);
    await userEvent.type(fecha, "2027-04-15");
    await userEvent.click(form.getByRole("button", { name: "Buscar vuelos" }));

    expect(await screen.findByRole("article", { name: /STA-00133/ })).toBeVisible();
    expect(within(pase("STA-00101")).getByText("Elegido")).toBeVisible();
    expect(router.state.location.search).toContain("ida=101");
    expect(ultima("/api/v1/busqueda/regresos").get("fecha")).toBe("2027-04-15");
  });

  it("al visitante agregar el trayecto lo lleva a iniciar sesión y conserva lo elegido en la dirección", async () => {
    responderApi(base({ [BUSCAR]: buscarVuelos([IDA_101]), [REGRESOS]: ok([REGRESO_132]) }));
    renderRutas(rutas, `/buscar/ida-y-regreso?${BUSQUEDA}`);

    await elegir("STA-00101", "ida");
    await elegir("STA-00132", "regreso");

    const enlace = await screen.findByRole("link", { name: "Inicia sesión para agregar" });
    const siguiente = new URL(enlace.getAttribute("href")!, "http://x").searchParams.get("next")!;
    expect(siguiente).toContain("ida=101");
    expect(siguiente).toContain("regreso_id=132");
    expect(siguiente).toContain("clase_ida=economica");
  });
});
