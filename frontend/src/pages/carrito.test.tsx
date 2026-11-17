import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Carrito, SeleccionCarrito } from "@/auth/carrito";
import { RequireRole } from "@/auth/require-role";
import { AppLayout } from "@/layouts/app-layout";
import { CarritoPage } from "@/pages/carrito";
import { CLIENTE, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

type Tramo = SeleccionCarrito["tramos"][number];
type Vuelo = Tramo["vuelo"];

const BOGOTA = "America/Bogota";
const NUEVA_YORK = "America/New_York";
const ciudad = (codigo: string, nombre: string, zona_horaria = BOGOTA) => ({
  codigo,
  nombre,
  zona_horaria,
});

/** Pereira → Bogotá, 15/04/2027 06:00 hora local (11:00Z), 50 min. */
const VUELO_131: Vuelo = {
  id: 131,
  codigo: "STA-00131",
  tipo: "nacional",
  origen: ciudad("PEI", "Pereira"),
  destino: ciudad("BOG", "Bogotá"),
  salida: "2027-04-15T11:00:00Z",
  llegada: "2027-04-15T11:50:00Z",
  duracion_minutos: 50,
  estado: "programado",
};
const VUELO_135: Vuelo = {
  ...VUELO_131,
  id: 135,
  codigo: "STA-00135",
  destino: ciudad("CTG", "Cartagena"),
  salida: "2027-04-18T15:00:00Z",
  llegada: "2027-04-18T16:05:00Z",
  duracion_minutos: 65,
};
/** Pereira → Nueva York, sale 08:00 de Pereira (13:00Z) y llega 14:30 de Nueva York (18:30Z). */
const VUELO_101: Vuelo = {
  ...VUELO_131,
  id: 101,
  codigo: "STA-00101",
  tipo: "internacional",
  destino: ciudad("JFK", "Nueva York", NUEVA_YORK),
  salida: "2027-04-15T13:00:00Z",
  llegada: "2027-04-15T18:30:00Z",
  duracion_minutos: 330,
};
const VUELO_132: Vuelo = {
  ...VUELO_131,
  id: 132,
  codigo: "STA-00132",
  tipo: "internacional",
  origen: ciudad("JFK", "Nueva York", NUEVA_YORK),
  destino: ciudad("CTG", "Cartagena"),
  salida: "2027-04-22T14:00:00Z",
  llegada: "2027-04-22T18:30:00Z",
  duracion_minutos: 270,
};

const tramo = (vuelo: Vuelo, cambios: Partial<Tramo> = {}): Tramo => ({
  vuelo,
  clase: "economica",
  precio_unitario: 262_500,
  precio_al_agregar: 262_500,
  promocion_porcentaje: null,
  disponibles: 12,
  tiquetes_activos: 0,
  ...cambios,
});

const seleccion = (
  id: number,
  tramos: Tramo[],
  cambios: Partial<SeleccionCarrito> = {},
): SeleccionCarrito => {
  const viajeros = cambios.viajeros ?? 2;
  return {
    id,
    tramos,
    viajeros,
    subtotal: tramos.reduce((suma, t) => suma + t.precio_unitario * viajeros, 0),
    confirmable: true,
    avisos: [],
    reserva_venceria_en: "2027-04-14T11:00:00Z",
    agregada_en: "2026-11-17T10:00:00Z",
    ...cambios,
  };
};

const carritoDe = (selecciones: SeleccionCarrito[]): Carrito => ({
  selecciones,
  cantidad: selecciones.length,
  total: selecciones.filter((s) => s.confirmable).reduce((suma, s) => suma + s.subtotal, 0),
});

const CARRITO = "GET /api/v1/carrito";
const VACIAR = "DELETE /api/v1/carrito";
const SELECCION_1 = "PATCH /api/v1/carrito/selecciones/1";
const QUITAR_1 = "DELETE /api/v1/carrito/selecciones/1";

const rutas = [
  { path: "/carrito", element: <CarritoPage /> },
  { path: "/buscar", element: <p>Buscador de vuelos</p> },
  { path: "/compra/viajeros", element: <p>Datos de los viajeros</p> },
];

/** Las peticiones que se hicieron con ese método y esa ruta. */
function llamadas(metodo: string, ruta: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => r.method === metodo && new URL(r.url).pathname === ruta);
}

/** Cuerpos JSON de esas peticiones. */
async function cuerpos(metodo: string, ruta: string) {
  return Promise.all(llamadas(metodo, ruta).map((r) => r.clone().json() as Promise<unknown>));
}

const error = (
  status: number,
  codigo: string,
  mensaje: string,
  campos?: Record<string, string>,
) => ({
  status,
  body: { error: { codigo, mensaje, campos } },
});

describe("S16 · Carrito (HU-22, HU-23)", () => {
  it("muestra cada selección con la ruta, las horas locales, el precio vigente y el subtotal", async () => {
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([seleccion(1, [tramo(VUELO_131)])]) },
    });
    renderRutas(rutas, "/carrito");

    const tarjeta = within(await screen.findByRole("region", { name: /STA-00131/ }));
    expect(tarjeta.getByText(/^Pereira/)).toBeVisible();
    expect(tarjeta.getByText(/^Bogotá/)).toBeVisible();
    expect(tarjeta.getByText("06:00")).toBeVisible();
    expect(tarjeta.getByText("06:50")).toBeVisible();
    expect(tarjeta.getByText("Salida 15/04/2027")).toBeVisible();
    expect(tarjeta.getByText("$ 262.500")).toBeVisible();
    expect(tarjeta.getByText("por viajero · Económica")).toBeVisible();
    expect(tarjeta.getByText("2 viajeros")).toBeVisible();
    expect(tarjeta.getByText("$ 525.000")).toBeVisible();
    expect(tarjeta.getByRole("combobox", { name: "Viajeros" })).toHaveValue("2");
    expect(tarjeta.getByRole("combobox", { name: "Clase" })).toHaveValue("economica");
  });

  it("HU-22: dice hasta cuándo quedarían congelados el precio y las sillas si se reserva ahora", async () => {
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([seleccion(1, [tramo(VUELO_131)])]) },
    });
    renderRutas(rutas, "/carrito");

    expect(
      await screen.findByText(/congelados hasta el 14\/04\/2027 06:00 \(hora de Colombia\)/),
    ).toBeVisible();
  });

  it("HU-23: advierte con el precio anterior y el nuevo cuando el precio cambió, y deja continuar", async () => {
    const cambiado = seleccion(
      1,
      [tramo(VUELO_131, { precio_unitario: 210_000, promocion_porcentaje: 20 })],
      {
        avisos: [
          {
            codigo: "precio_cambio",
            tramo: 0,
            mensaje: "El precio cambió de $ 262.500 a $ 210.000. Pagarás el precio nuevo.",
          },
        ],
      },
    );
    responderApi({ [CARRITO]: { status: 200, body: carritoDe([cambiado]) } });
    renderRutas(rutas, "/carrito");

    const tarjeta = within(await screen.findByRole("region", { name: /STA-00131/ }));
    expect(tarjeta.getByText(/El precio cambió de \$ 262\.500 a \$ 210\.000/)).toBeVisible();
    expect(tarjeta.getByText("$ 262.500", { selector: ".sta-pass__old" })).toBeVisible();
    expect(tarjeta.getByText("$ 210.000", { selector: ".sta-pass__price" })).toBeVisible();
    expect(tarjeta.getByText("Promoción −20 %")).toBeVisible();
    expect(tarjeta.getByRole("link", { name: "Continuar con los viajeros" })).toBeVisible();
  });

  it("HU-23: una selección sin disponibilidad se advierte y no se puede confirmar", async () => {
    const agotada = seleccion(1, [tramo(VUELO_131, { disponibles: 0 })], {
      confirmable: false,
      reserva_venceria_en: null,
      avisos: [
        {
          codigo: "clase_agotada",
          tramo: 0,
          mensaje:
            "Ya no quedan sillas suficientes en Económica. Cambia de clase o quita este vuelo.",
        },
      ],
    });
    const libre = seleccion(2, [tramo(VUELO_135)]);
    responderApi({ [CARRITO]: { status: 200, body: carritoDe([agotada, libre]) } });
    renderRutas(rutas, "/carrito");

    const tarjeta = within(await screen.findByRole("region", { name: /STA-00131/ }));
    expect(tarjeta.getByText(/Ya no quedan sillas suficientes en Económica/)).toBeVisible();
    expect(tarjeta.getByText("No se puede continuar")).toBeVisible();
    expect(tarjeta.getByRole("button", { name: "Continuar con los viajeros" })).toBeDisabled();
    expect(tarjeta.queryByRole("link", { name: "Continuar con los viajeros" })).toBeNull();
    // El total no suma lo que no se puede confirmar.
    expect(screen.getByText("$ 525.000", { selector: ".sta-glass--inset .price" })).toBeVisible();
  });

  it("confirmar una selección lleva a los datos de los viajeros de esa selección", async () => {
    responderApi({
      [CARRITO]: {
        status: 200,
        body: carritoDe([seleccion(1, [tramo(VUELO_131)]), seleccion(2, [tramo(VUELO_135)])]),
      },
    });
    const { router } = renderRutas(rutas, "/carrito");

    const tarjeta = within(await screen.findByRole("region", { name: /STA-00135/ }));
    await userEvent.click(tarjeta.getByRole("link", { name: "Continuar con los viajeros" }));

    expect(router.state.location.pathname).toBe("/compra/viajeros");
    expect(router.state.location.search).toBe("?seleccion=2");
  });

  it("un trayecto completo es una sola selección con sus dos tramos y la suma de los precios", async () => {
    const completo = seleccion(
      1,
      [
        tramo(VUELO_101, { precio_unitario: 1_650_000 }),
        tramo(VUELO_132, { precio_unitario: 1_750_000, clase: "primera" }),
      ],
      { viajeros: 1 },
    );
    responderApi({ [CARRITO]: { status: 200, body: carritoDe([completo]) } });
    renderRutas(rutas, "/carrito");

    const tarjeta = within(await screen.findByRole("region", { name: /Trayecto completo/ }));
    expect(tarjeta.getByText("IDA")).toBeVisible();
    expect(tarjeta.getByText("REGRESO")).toBeVisible();
    expect(tarjeta.getByText("STA-00101")).toBeVisible();
    expect(tarjeta.getByText("STA-00132")).toBeVisible();
    // La llegada es en la hora local de Nueva York (IU-05).
    expect(tarjeta.getByText("14:30")).toBeVisible();
    expect(tarjeta.getByText("$ 3.400.000", { selector: ".price" })).toBeVisible();
    expect(tarjeta.getByText("1 viajero, ida y regreso")).toBeVisible();
    expect(tarjeta.getByRole("combobox", { name: "Clase de la ida" })).toHaveValue("economica");
    expect(tarjeta.getByRole("combobox", { name: "Clase del regreso" })).toHaveValue("primera");
    expect(screen.getAllByRole("region")).toHaveLength(1);
  });

  it("HU-23: cambiar la clase de un tramo envía una clase por tramo, en orden", async () => {
    const completo = seleccion(1, [tramo(VUELO_101), tramo(VUELO_132)], { viajeros: 1 });
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([completo]) },
      [SELECCION_1]: { status: 200, body: completo },
    });
    renderRutas(rutas, "/carrito");

    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: "Clase del regreso" }),
      "primera",
    );

    await waitFor(async () =>
      expect(await cuerpos("PATCH", "/api/v1/carrito/selecciones/1")).toEqual([
        { clases: ["economica", "primera"] },
      ]),
    );
  });

  it("HU-23: cambiar la cantidad de viajeros la envía al servidor", async () => {
    const inicial = seleccion(1, [tramo(VUELO_131)]);
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([inicial]) },
      [SELECCION_1]: { status: 200, body: inicial },
    });
    renderRutas(rutas, "/carrito");

    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Viajeros" }), "4");

    await waitFor(async () =>
      expect(await cuerpos("PATCH", "/api/v1/carrito/selecciones/1")).toEqual([{ viajeros: 4 }]),
    );
  });

  it("HU-22: clase_agotada al cambiar la clase se muestra en la selección y la clase vuelve a la anterior", async () => {
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([seleccion(1, [tramo(VUELO_131)])]) },
      [SELECCION_1]: error(409, "clase_agotada", "No quedan sillas suficientes en esta clase."),
    });
    renderRutas(rutas, "/carrito");

    const tarjeta = within(await screen.findByRole("region", { name: /STA-00131/ }));
    await userEvent.selectOptions(tarjeta.getByRole("combobox", { name: "Clase" }), "primera");

    expect(await tarjeta.findByText("No quedan sillas suficientes en esta clase.")).toBeVisible();
    expect(tarjeta.getByRole("combobox", { name: "Clase" })).toHaveValue("economica");
  });

  it("HU-22: limite_tiquetes al cambiar la cantidad se muestra en la selección", async () => {
    responderApi({
      [CARRITO]: {
        status: 200,
        body: carritoDe([seleccion(1, [tramo(VUELO_135)], { viajeros: 1 })]),
      },
      [SELECCION_1]: error(
        409,
        "limite_tiquetes",
        "Un cliente puede tener máximo 5 tiquetes activos en el mismo vuelo.",
      ),
    });
    renderRutas(rutas, "/carrito");

    const tarjeta = within(await screen.findByRole("region", { name: /STA-00135/ }));
    await userEvent.selectOptions(tarjeta.getByRole("combobox", { name: "Viajeros" }), "5");

    expect(await tarjeta.findByText(/máximo 5 tiquetes activos/)).toBeVisible();
    expect(tarjeta.getByRole("combobox", { name: "Viajeros" })).toHaveValue("1");
  });

  it("HU-23: quitar una selección la saca de inmediato y deja las demás", async () => {
    let actual = carritoDe([seleccion(1, [tramo(VUELO_131)]), seleccion(2, [tramo(VUELO_135)])]);
    responderApi({
      [CARRITO]: () => ({ status: 200, body: actual }),
      [QUITAR_1]: () => {
        actual = carritoDe(actual.selecciones.filter((s) => s.id !== 1));
        return { status: 204 };
      },
    });
    renderRutas(rutas, "/carrito");

    await userEvent.click(
      await screen.findByRole("button", { name: "Quitar STA-00131 del carrito" }),
    );
    const dialogo = within(
      await screen.findByRole("dialog", { name: "¿Quitar el vuelo STA-00131?" }),
    );
    expect(dialogo.getByText(/Solo se quita esta selección/)).toBeVisible();
    await userEvent.click(dialogo.getByRole("button", { name: "Quitar del carrito" }));

    await waitFor(() => expect(screen.queryByRole("region", { name: /STA-00131/ })).toBeNull());
    expect(screen.getByRole("region", { name: /STA-00135/ })).toBeVisible();
    expect(llamadas("DELETE", "/api/v1/carrito/selecciones/1")).toHaveLength(1);
  });

  it("HU-23: quitar una selección pide confirmación y no borra nada si se vuelve", async () => {
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([seleccion(1, [tramo(VUELO_131)])]) },
      [QUITAR_1]: { status: 204 },
    });
    renderRutas(rutas, "/carrito");

    await userEvent.click(
      await screen.findByRole("button", { name: "Quitar STA-00131 del carrito" }),
    );
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Volver" }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("region", { name: /STA-00131/ })).toBeVisible();
    expect(llamadas("DELETE", "/api/v1/carrito/selecciones/1")).toHaveLength(0);
  });

  it("HU-23: quitar un trayecto completo pregunta por la ruta entera", async () => {
    const completo = seleccion(1, [tramo(VUELO_101), tramo(VUELO_132)], { viajeros: 1 });
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([completo]) },
      [QUITAR_1]: { status: 204 },
    });
    renderRutas(rutas, "/carrito");

    await userEvent.click(
      await screen.findByRole("button", { name: "Quitar STA-00101 y STA-00132 del carrito" }),
    );

    const dialogo = within(
      await screen.findByRole("dialog", { name: "¿Quitar el trayecto completo?" }),
    );
    expect(
      dialogo.getByText(/Pereira → Nueva York → Cartagena \(STA-00101 y STA-00132\)/),
    ).toBeVisible();
  });

  it("HU-23: vaciar el carrito pide confirmación y no borra nada si se vuelve", async () => {
    responderApi({
      [CARRITO]: { status: 200, body: carritoDe([seleccion(1, [tramo(VUELO_131)])]) },
      [VACIAR]: { status: 204 },
    });
    renderRutas(rutas, "/carrito");

    await userEvent.click(await screen.findByRole("button", { name: /Vaciar carrito/ }));
    const dialogo = within(await screen.findByRole("dialog", { name: "¿Vaciar el carrito?" }));
    expect(dialogo.getByText(/Hay 1 selección/)).toBeVisible();
    await userEvent.click(dialogo.getByRole("button", { name: "Volver" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("region", { name: /STA-00131/ })).toBeVisible();
    expect(llamadas("DELETE", "/api/v1/carrito")).toHaveLength(0);
  });

  it("HU-23: confirmar el vaciado deja el estado vacío que lleva a buscar vuelos", async () => {
    let actual = carritoDe([seleccion(1, [tramo(VUELO_131)]), seleccion(2, [tramo(VUELO_135)])]);
    responderApi({
      [CARRITO]: () => ({ status: 200, body: actual }),
      [VACIAR]: () => {
        actual = carritoDe([]);
        return { status: 204 };
      },
    });
    const { router } = renderRutas(rutas, "/carrito");

    await userEvent.click(await screen.findByRole("button", { name: /Vaciar carrito/ }));
    const dialogo = within(await screen.findByRole("dialog"));
    expect(dialogo.getByText(/Hay 2 selecciones/)).toBeVisible();
    await userEvent.click(dialogo.getByRole("button", { name: "Vaciar carrito" }));

    expect(await screen.findByText("Tu carrito está vacío")).toBeVisible();
    expect(screen.queryByRole("region")).toBeNull();
    expect(screen.queryByRole("button", { name: /Vaciar carrito/ })).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "Buscar vuelos" }));
    expect(router.state.location.pathname).toBe("/buscar");
  });

  it("con el carrito vacío muestra el estado vacío y no ofrece vaciar", async () => {
    responderApi({ [CARRITO]: { status: 200, body: carritoDe([]) } });
    renderRutas(rutas, "/carrito");

    expect(await screen.findByText("Tu carrito está vacío")).toBeVisible();
    expect(screen.getByRole("link", { name: "Buscar vuelos" })).toHaveAttribute("href", "/buscar");
    expect(screen.queryByRole("button", { name: /Vaciar carrito/ })).toBeNull();
  });

  it("si no se puede leer el carrito, dice por qué y deja reintentar", async () => {
    responderApi({ [CARRITO]: error(500, "error_interno", "Algo salió mal. Intenta de nuevo.") });
    renderRutas(rutas, "/carrito");

    expect(await screen.findByText("Algo salió mal. Intenta de nuevo.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeVisible();
  });
});

describe("Contador del carrito en el menú (HU-23)", () => {
  const conLayout = [
    {
      element: <AppLayout />,
      children: [
        {
          element: <RequireRole roles={["cliente"]} />,
          children: [{ path: "/carrito", element: <CarritoPage /> }],
        },
      ],
    },
  ];

  it("muestra cuántas selecciones hay y baja al quitar una", async () => {
    let actual = carritoDe([seleccion(1, [tramo(VUELO_131)]), seleccion(2, [tramo(VUELO_135)])]);
    responderApi({
      "GET /api/v1/auth/me": sesionDe(CLIENTE),
      "GET /api/v1/usuarios/me/perfil": { status: 200, body: {} },
      [CARRITO]: () => ({ status: 200, body: actual }),
      [QUITAR_1]: () => {
        actual = carritoDe(actual.selecciones.filter((s) => s.id !== 1));
        return { status: 204 };
      },
    });
    renderRutas(conLayout, "/carrito");

    expect(await screen.findByRole("link", { name: "Carrito, 2 selecciones" })).toBeVisible();
    await userEvent.click(
      await screen.findByRole("button", { name: "Quitar STA-00131 del carrito" }),
    );
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Quitar del carrito" }),
    );

    expect(await screen.findByRole("link", { name: "Carrito, 1 selección" })).toBeVisible();
  });
});
