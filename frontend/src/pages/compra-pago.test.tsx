import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CompraPagoPage } from "@/pages/compra-pago";
import type { Compra } from "@/pages/compra-pago/api";
import { responderApi } from "@/test/api";
import { renderRutas } from "@/test/render";

type Vuelo = Compra["tramos"][number]["vuelo"];

const BOGOTA = "America/Bogota";
const ciudad = (codigo: string, nombre: string, zona_horaria = BOGOTA) => ({
  codigo,
  nombre,
  zona_horaria,
});

/** Pereira → Cartagena, 20/04/2027 09:15 hora local (14:15Z), 1 h 30 min. */
const VUELO_160: Vuelo = {
  id: 160,
  codigo: "STA-00160",
  tipo: "nacional",
  origen: ciudad("PEI", "Pereira"),
  destino: ciudad("CTG", "Cartagena"),
  salida: "2027-04-20T14:15:00Z",
  llegada: "2027-04-20T15:45:00Z",
  duracion_minutos: 90,
  estado: "programado",
};
const VUELO_101: Vuelo = {
  ...VUELO_160,
  id: 101,
  codigo: "STA-00101",
  tipo: "internacional",
  destino: ciudad("JFK", "Nueva York", "America/New_York"),
  salida: "2027-04-15T13:00:00Z",
  llegada: "2027-04-15T18:30:00Z",
  duracion_minutos: 330,
};
const VUELO_132: Vuelo = {
  ...VUELO_160,
  id: 132,
  codigo: "STA-00132",
  tipo: "internacional",
  origen: ciudad("JFK", "Nueva York", "America/New_York"),
  destino: ciudad("CTG", "Cartagena"),
  salida: "2027-04-22T14:00:00Z",
  llegada: "2027-04-22T18:20:00Z",
  duracion_minutos: 320,
};

const viajero = (
  id: number,
  nombres: string,
  apellidos: string,
  tiquetes: [number, string, number][],
) => ({
  id,
  tipo_documento: "CC" as const,
  numero_documento: `10${id}`,
  nombres,
  apellidos,
  fecha_nacimiento: "1995-03-14",
  genero: "femenino" as const,
  telefono: "310 555 0192",
  email: `${nombres.toLowerCase()}@correo.co`,
  contacto_nombre: "Jorge Gómez",
  contacto_telefono: "311 555 0101",
  tiquetes: tiquetes.map(([tramo, silla, precio], i) => ({
    id: id * 10 + i,
    tramo,
    clase: "economica" as const,
    silla,
    numero_silla: 1,
    precio,
    estado: "bloqueado" as const,
  })),
});

const enSegundos = (s: number) => new Date(Date.now() + s * 1000).toISOString();

/** K7Q2PX: 2 viajeros × $ 400.000 con las sillas 18C y 18D bloqueadas 14 min 32 s. */
const compra = (cambios: Partial<Compra> = {}): Compra =>
  ({
    id: 901,
    tipo: "compra",
    codigo: "K7Q2PX",
    estado: "pendiente",
    reserva_id: null,
    compra_id: null,
    creada_en: "2027-04-01T10:00:00Z",
    vence_en: enSegundos(14 * 60 + 32),
    pagada_en: null,
    total: 800_000,
    total_pendiente: 800_000,
    tramos: [{ vuelo: VUELO_160 }],
    viajeros: [
      viajero(1, "Laura", "Gómez", [[0, "18C", 400_000]]),
      viajero(2, "Marta", "Ríos", [[0, "18D", 400_000]]),
    ],
    ...cambios,
  }) as Compra;

/** La compra y su cobro: GET devuelve el estado actual y confirmar la deja pagada, como el servidor. */
function conCobro() {
  let actual = compra();
  return {
    [COMPRA]: () => ({ status: 200, body: actual }),
    [CONFIRMAR]: () => {
      actual = compra({
        estado: "activa",
        vence_en: null,
        total_pendiente: 0,
        pagada_en: "2027-04-01T10:05:00Z",
      });
      return { status: 200, body: actual };
    },
  };
}

const COMPRA = "GET /api/v1/compras/901";
const CONFIRMAR = "POST /api/v1/compras/901/confirmar";
const SOLTAR = "DELETE /api/v1/compras/901";
const MONEDERO = "GET /api/v1/monedero";
const QUITAR = "DELETE /api/v1/carrito/selecciones/71";

const error = (status: number, codigo: string, mensaje: string) => ({
  status,
  body: { error: { codigo, mensaje } },
});

const rutas = [
  { path: "/compra/pago/:compraId", element: <CompraPagoPage /> },
  { path: "/carrito", element: <p>Tu carrito</p> },
  { path: "/mis-viajes", element: <p>Mis viajes</p> },
];

const abrir = (url = "/compra/pago/901?seleccion=71") => renderRutas(rutas, url);
const llamadas = (metodo: string, ruta: string) =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => r.method === metodo && new URL(r.url).pathname === ruta);

describe("S18 · Pago con monedero (HU-25, HU-26)", () => {
  it("muestra el paso Pago, las sillas asignadas, el total, el saldo actual y el saldo después", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra() },
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();

    expect(await screen.findByRole("heading", { name: "Paga con tu monedero" })).toBeVisible();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Pago");
    const pase = within(screen.getByRole("article", { name: /STA-00160/ }));
    expect(pase.getByText("09:15")).toBeVisible();
    expect(pase.getByText("10:45")).toBeVisible();
    expect(pase.getByText(/Laura Gómez y Marta Ríos/)).toBeVisible();
    expect(pase.getByText("18C y 18D")).toBeVisible();
    expect(pase.getByText("2 × $ 400.000, económica")).toBeVisible();
    expect(pase.getByText("$ 800.000", { selector: ".sta-pass__price" })).toBeVisible();

    const panel = within((await screen.findByText("Tu monedero")).closest("section")!);
    expect(await panel.findByText("$ 1.000.000")).toBeVisible();
    expect(panel.getByText("− $ 800.000")).toBeVisible();
    expect(panel.getByText("$ 200.000")).toBeVisible();
    expect(panel.getByRole("button", { name: "Pagar $ 800.000" })).toBeEnabled();
  });

  it("HU-25: la cuenta regresiva muestra el tiempo que queda", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra() },
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();

    expect(await screen.findByText(/Sillas bloqueadas por 14:3[12] minutos/)).toBeVisible();
    expect(screen.getByText(/Si no confirmas, se liberan para otros clientes/)).toBeVisible();
  });

  it("HU-25: al llegar a cero avisa que las sillas se liberaron y ofrece empezar de nuevo", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra({ vence_en: enSegundos(1.5) }) },
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();
    await screen.findByText(/Sillas bloqueadas por/);

    expect(
      await screen.findByText(
        /Las sillas se liberaron porque pasaron 15 minutos/,
        {},
        { timeout: 4000 },
      ),
    ).toBeVisible();
    expect(screen.getByText(/No te cobramos nada/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Empezar de nuevo" })).toHaveAttribute(
      "href",
      "/carrito",
    );
    expect(screen.queryByRole("button", { name: /Pagar/ })).toBeNull();
  });

  it("HU-25: con saldo insuficiente dice cuánto falta y lleva a recargar ese valor y volver aquí", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra() },
      [MONEDERO]: { status: 200, body: { saldo: 500_000 } },
    });
    abrir();

    expect(await screen.findByText(/Te faltan \$ 300\.000/)).toBeVisible();
    expect(screen.getByText(/sin perder tus sillas/)).toBeVisible();
    const recargar = screen.getByRole("link", { name: "Recargar $ 300.000" });
    expect(recargar).toHaveAttribute(
      "href",
      "/monedero/recargar?faltante=300000&codigo=K7Q2PX&volver=%2Fcompra%2Fpago%2F901%3Fseleccion%3D71",
    );
    expect(screen.getByRole("button", { name: "Pagar $ 800.000" })).toBeDisabled();
    expect(screen.getByText("No alcanza")).toBeVisible();
  });

  it("HU-25: al confirmar muestra el código de reserva, avisa del correo y quita la selección del carrito", async () => {
    responderApi({
      ...conCobro(),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [QUITAR]: { status: 204 },
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: "Pagar $ 800.000" }));

    expect(await screen.findByRole("heading", { name: "Compra pagada" })).toBeVisible();
    expect(screen.getByLabelText("Código de reserva K7Q2PX")).toBeVisible();
    expect(screen.getByText(/comprobante en PDF a tu correo/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Ver mis viajes" })).toHaveAttribute(
      "href",
      "/mis-viajes?tipo=compra",
    );
    await waitFor(() =>
      expect(llamadas("DELETE", "/api/v1/carrito/selecciones/71")).toHaveLength(1),
    );
    expect(llamadas("POST", "/api/v1/compras/901/confirmar")).toHaveLength(1);
  });

  it("sin ?seleccion no hay selección que quitar del carrito", async () => {
    responderApi({ ...conCobro(), [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } } });
    abrir("/compra/pago/901");

    await userEvent.click(await screen.findByRole("button", { name: "Pagar $ 800.000" }));

    expect(await screen.findByRole("heading", { name: "Compra pagada" })).toBeVisible();
    expect(llamadas("DELETE", "/api/v1/carrito/selecciones/71")).toHaveLength(0);
  });

  it("HU-25: bloqueo_vencido al confirmar informa, no cobra y ofrece empezar de nuevo", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra() },
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [CONFIRMAR]: error(
        409,
        "bloqueo_vencido",
        "Las sillas se liberaron porque pasaron 15 minutos sin confirmar. Vuelve a empezar la compra.",
      ),
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: "Pagar $ 800.000" }));

    expect(await screen.findByText(/No te cobramos nada/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Empezar de nuevo" })).toBeVisible();
    expect(llamadas("DELETE", "/api/v1/carrito/selecciones/71")).toHaveLength(0);
  });

  it("si el saldo cambió y el servidor responde saldo_insuficiente, vuelve a leer el saldo y muestra lo que falta", async () => {
    let saldo = 1_000_000;
    responderApi({
      [COMPRA]: { status: 200, body: compra() },
      [MONEDERO]: () => ({ status: 200, body: { saldo } }),
      [CONFIRMAR]: () => {
        saldo = 500_000;
        return error(409, "saldo_insuficiente", "Tu saldo no alcanza: te faltan $ 300.000.");
      },
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: "Pagar $ 800.000" }));

    expect(await screen.findByText(/Te faltan \$ 300\.000\. Recarga tu monedero/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Recargar $ 300.000" })).toBeVisible();
  });

  it("HU-02: sin el correo verificado avisa y ofrece reenviar la verificación", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra() },
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [CONFIRMAR]: error(
        403,
        "correo_no_verificado",
        "Verifica tu correo para reservar o comprar.",
      ),
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: "Pagar $ 800.000" }));

    expect(await screen.findByText("Verifica tu correo para reservar o comprar.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Reenviar la verificación" })).toBeVisible();
  });

  it("cancelar pide confirmación, suelta el bloqueo y vuelve al carrito", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra() },
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [SOLTAR]: { status: 204 },
    });
    const { router } = abrir();

    await userEvent.click(await screen.findByRole("button", { name: "Cancelar compra" }));
    const dialogo = within(
      await screen.findByRole("dialog", { name: "¿Cancelar la compra K7Q2PX?" }),
    );
    await userEvent.click(dialogo.getByRole("button", { name: "Volver" }));
    expect(llamadas("DELETE", "/api/v1/compras/901")).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Cancelar compra" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancelar compra" }),
    );

    await waitFor(() => expect(router.state.location.pathname).toBe("/carrito"));
    expect(llamadas("DELETE", "/api/v1/compras/901")).toHaveLength(1);
  });

  it("HU-26: un trayecto completo muestra los dos tramos bajo un solo pago", async () => {
    responderApi({
      [COMPRA]: {
        status: 200,
        body: compra({
          total: 3_400_000,
          total_pendiente: 3_400_000,
          tramos: [{ vuelo: VUELO_101 }, { vuelo: VUELO_132 }],
          viajeros: [
            viajero(1, "Laura", "Gómez", [
              [0, "12A", 1_650_000],
              [1, "9C", 1_750_000],
            ]),
          ],
        }),
      },
      [MONEDERO]: { status: 200, body: { saldo: 5_000_000 } },
    });
    abrir();

    expect(await screen.findByRole("article", { name: /STA-00101/ })).toBeVisible();
    expect(screen.getByRole("article", { name: /STA-00132/ })).toBeVisible();
    expect(screen.getByText("IDA")).toBeVisible();
    expect(screen.getByText("REGRESO")).toBeVisible();
    expect(screen.getByText("12A")).toBeVisible();
    expect(screen.getByText("9C")).toBeVisible();
    expect(screen.getAllByRole("button", { name: /^Pagar / })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Pagar $ 3.400.000" })).toBeVisible();
  });

  it("una compra ya pagada muestra el código y no ofrece pagar otra vez", async () => {
    responderApi({
      [COMPRA]: {
        status: 200,
        body: compra({ estado: "activa", vence_en: null, total_pendiente: 0 }),
      },
      [MONEDERO]: { status: 200, body: { saldo: 200_000 } },
    });
    abrir();

    expect(await screen.findByRole("heading", { name: "Compra pagada" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Pagar/ })).toBeNull();
  });

  it("una compra vencida o soltada dice que las sillas se liberaron", async () => {
    responderApi({
      [COMPRA]: { status: 200, body: compra({ estado: "vencida" }) },
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();

    expect(
      await screen.findByText(/Las sillas se liberaron porque pasaron 15 minutos/),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Empezar de nuevo" })).toBeVisible();
  });

  it("una compra que no existe o es de otro cliente dice que no existe", async () => {
    responderApi({
      [COMPRA]: error(404, "no_encontrado", "La compra no existe."),
      [MONEDERO]: { status: 200, body: { saldo: 0 } },
    });
    abrir("/compra/pago/901");

    expect(await screen.findByText(/La compra no existe/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Volver al carrito" })).toHaveAttribute(
      "href",
      "/carrito",
    );
  });
});
