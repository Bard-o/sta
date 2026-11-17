import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MisViajesPage } from "@/pages/mis-viajes";
import type { Viaje } from "@/pages/mis-viajes/api";
import { responderApi } from "@/test/api";
import { renderRutas } from "@/test/render";

type Vuelo = Viaje["tramos"][number]["vuelo"];

const BOGOTA = "America/Bogota";
const ciudad = (codigo: string, nombre: string, zona_horaria = BOGOTA) => ({
  codigo,
  nombre,
  zona_horaria,
});

/** Pereira → Bogotá, 15/04/2027 06:00 hora local (11:00Z). */
const VUELO_131: Vuelo = {
  id: 131,
  codigo: "STA-00131",
  tipo: "nacional",
  origen: ciudad("PEI", "Pereira"),
  destino: ciudad("BOG", "Bogotá"),
  salida: "2027-04-15T11:00:00Z",
  llegada: "2027-04-15T11:55:00Z",
  duracion_minutos: 55,
  estado: "programado",
};
const VUELO_142: Vuelo = {
  ...VUELO_131,
  id: 142,
  codigo: "STA-00142",
  destino: ciudad("MDE", "Medellín"),
  salida: "2027-04-02T12:40:00Z",
  llegada: "2027-04-02T13:25:00Z",
  duracion_minutos: 45,
};
const VUELO_101: Vuelo = {
  ...VUELO_131,
  id: 101,
  codigo: "STA-00101",
  tipo: "internacional",
  destino: ciudad("JFK", "Nueva York", "America/New_York"),
  salida: "2027-04-15T13:00:00Z",
  llegada: "2027-04-15T18:30:00Z",
  duracion_minutos: 330,
};
const VUELO_132: Vuelo = {
  ...VUELO_131,
  id: 132,
  codigo: "STA-00132",
  tipo: "internacional",
  origen: ciudad("JFK", "Nueva York", "America/New_York"),
  destino: ciudad("CTG", "Cartagena"),
  salida: "2027-04-22T14:00:00Z",
  llegada: "2027-04-22T18:20:00Z",
  duracion_minutos: 320,
};

type Estado = "reservado" | "comprado" | "vencido" | "cancelado";
const viajero = (
  id: number,
  nombres: string,
  apellidos: string,
  tiquetes: [number, string, number, Estado][],
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
  tiquetes: tiquetes.map(([tramo, silla, precio, estado], i) => ({
    id: id * 10 + i,
    tramo,
    clase: "economica" as const,
    silla,
    numero_silla: 1,
    precio,
    estado,
  })),
});

const enMinutos = (m: number) => new Date(Date.now() + m * 60_000 + 30_000).toISOString();

/** H4N8WQ: tres viajeros reservados a $ 262.500 (precio congelado; hoy el vuelo tiene otro). */
const reserva = (cambios: Partial<Viaje> = {}): Viaje =>
  ({
    id: 41,
    tipo: "reserva",
    codigo: "H4N8WQ",
    estado: "vigente",
    reserva_id: null,
    compra_id: null,
    creada_en: "2027-04-01T10:00:00Z",
    vence_en: enMinutos(5 * 60 + 12),
    pagada_en: null,
    total: 787_500,
    total_pendiente: 787_500,
    tramos: [{ vuelo: VUELO_131 }],
    viajeros: [
      viajero(4101, "Laura", "Gómez", [[0, "18C", 262_500, "reservado"]]),
      viajero(4102, "Marta", "Ríos", [[0, "18D", 262_500, "reservado"]]),
      viajero(4103, "Tomás", "Gómez", [[0, "18E", 262_500, "reservado"]]),
    ],
    ...cambios,
  }) as Viaje;

const VENCIDA = reserva({
  id: 42,
  codigo: "B3M9TA",
  estado: "vencida",
  vence_en: "2027-04-01T14:02:00Z",
  total: 185_000,
  total_pendiente: 0,
  tramos: [{ vuelo: VUELO_142 }],
  viajeros: [viajero(4201, "Camilo", "Ríos", [[0, "9A", 185_000, "vencido"]])],
});

const compra = (cambios: Partial<Viaje> = {}): Viaje =>
  ({
    ...reserva(),
    id: 71,
    tipo: "compra",
    codigo: "R5T2LM",
    estado: "activa",
    vence_en: null,
    pagada_en: "2027-04-01T15:30:00Z",
    total: 525_000,
    total_pendiente: 0,
    viajeros: [
      viajero(7101, "Camilo", "Ríos", [[0, "12A", 262_500, "comprado"]]),
      viajero(7102, "Lucía", "Ríos", [[0, "12B", 262_500, "comprado"]]),
    ],
    ...cambios,
  }) as Viaje;

const pagina = (items: Viaje[]) => ({ items, total: items.length, pagina: 1, por_pagina: 20 });
const ok = (items: Viaje[]) => ({ status: 200, body: pagina(items) });
const error = (
  status: number,
  codigo: string,
  mensaje: string,
  campos?: Record<string, string>,
) => ({
  status,
  body: { error: { codigo, mensaje, campos } },
});

const MIS_VIAJES = "GET /api/v1/mis-viajes";
const MONEDERO = "GET /api/v1/monedero";
const PAGAR = "POST /api/v1/reservas/41/pagar";

const rutas = [
  { path: "/mis-viajes", element: <MisViajesPage /> },
  { path: "/buscar", element: <p>Buscador de vuelos</p> },
];

const abrir = (url = "/mis-viajes?tipo=reserva") => renderRutas(rutas, url);
const consultas = () =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => new URL((r as Request).url))
    .filter((u) => u.pathname === "/api/v1/mis-viajes");
const ultima = () => consultas().at(-1)!.searchParams;
const pagos = () =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => r.method === "POST" && new URL(r.url).pathname === "/api/v1/reservas/41/pagar");

const tarjeta = async (nombre: string) =>
  within(await screen.findByRole("group", { name: nombre }));

describe("S19 · Mis viajes (HU-27)", () => {
  it("lista las reservas con su vuelo, viajeros, sillas, precio congelado y cuánto falta para vencer", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva(), VENCIDA]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();

    const r = await tarjeta("Reserva H4N8WQ");
    expect(await r.findByText("RES H4N8WQ")).toBeVisible();
    expect(r.getByText("06:00")).toBeVisible();
    expect(r.getByText(/^Pereira/)).toBeVisible();
    expect(r.getByText(/Vence en 5 h 12 min/)).toBeVisible();
    expect(r.getByText(/\(\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}\)\. Precio congelado\./)).toBeVisible();
    expect(r.getByText("Vigente")).toBeVisible();
    expect(screen.getByText(/Laura Gómez, 18C/)).toBeVisible();
    expect(screen.getByText(/Marta Ríos, 18D/)).toBeVisible();
    expect(screen.getByText(/Tomás Gómez, 18E/)).toBeVisible();
    expect(r.getByText("$ 787.500", { selector: ".sta-pass__price" })).toBeVisible();
    expect(r.getByText("3 de 3 seleccionados")).toBeVisible();
    const q = ultima();
    expect(q.get("tipo")).toBe("reserva");
    expect(q.get("por_pagina")).toBe("20");
  });

  it("la pestaña Compras lista las compras con sus viajeros, sillas, clase y precio", async () => {
    responderApi({
      [MIS_VIAJES]: (url: URL) =>
        ok(url.searchParams.get("tipo") === "compra" ? [compra()] : [reserva()]),
      [MONEDERO]: { status: 200, body: { saldo: 0 } },
    });
    abrir();
    await screen.findByText("RES H4N8WQ");

    await userEvent.click(screen.getByRole("button", { name: "Compras" }));

    const c = await tarjeta("Compra R5T2LM");
    expect(await c.findByText("COMPRA R5T2LM")).toBeVisible();
    expect(c.getByText("Activa")).toBeVisible();
    expect(c.getByText(/Pagada el \d{2}\/\d{2}\/\d{4}/)).toBeVisible();
    expect(c.getByText("Camilo Ríos: 12A, económica, $ 262.500")).toBeVisible();
    expect(c.getByText("Lucía Ríos: 12B, económica, $ 262.500")).toBeVisible();
    expect(ultima().get("tipo")).toBe("compra");
    expect(screen.queryByRole("button", { name: "Vigentes" })).toBeNull();
  });

  it("HU-27: se puede pagar la reserva completa al precio congelado", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva()]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [PAGAR]: { status: 200, body: { reserva: reserva(), compra: compra() } },
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: /Pagar 3 viajeros/ }));

    await waitFor(() => expect(pagos()).toHaveLength(1));
    expect(await pagos()[0].clone().json()).toEqual({ viajero_ids: [4101, 4102, 4103] });
  });

  it("HU-27: se puede elegir viajeros: pagar 2 de 3 envía solo esos y cambia el monto", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva()]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [PAGAR]: { status: 200, body: { reserva: reserva(), compra: compra() } },
    });
    abrir();
    const r = await tarjeta("Reserva H4N8WQ");

    await userEvent.click(await r.findByRole("checkbox", { name: /Tomás Gómez, 18E/ }));

    expect(r.getByText("2 de 3 seleccionados")).toBeVisible();
    expect(r.getByText("$ 525.000", { selector: ".sta-pass__price" })).toBeVisible();
    expect(
      screen.getByText(
        /Si pagas solo algunos viajeros, los demás siguen reservados con el mismo vencimiento/,
      ),
    ).toBeVisible();
    await userEvent.click(r.getByRole("button", { name: /Pagar 2 viajeros/ }));

    await waitFor(() => expect(pagos()).toHaveLength(1));
    expect(await pagos()[0].clone().json()).toEqual({ viajero_ids: [4101, 4102] });
  });

  it("sin ningún viajero elegido no se puede pagar", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva({ viajeros: reserva().viajeros.slice(0, 1) })]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();

    await userEvent.click(await screen.findByRole("checkbox", { name: /Laura Gómez, 18C/ }));

    expect(screen.getByRole("button", { name: /Pagar 0 viajeros/ })).toBeDisabled();
  });

  it("después de pagar a algunos, los pagados salen sin casilla y los demás siguen reservados", async () => {
    let actual = reserva();
    responderApi({
      [MIS_VIAJES]: () => ok([actual]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [PAGAR]: () => {
        actual = reserva({
          total_pendiente: 262_500,
          viajeros: [
            viajero(4101, "Laura", "Gómez", [[0, "18C", 262_500, "comprado"]]),
            viajero(4102, "Marta", "Ríos", [[0, "18D", 262_500, "comprado"]]),
            viajero(4103, "Tomás", "Gómez", [[0, "18E", 262_500, "reservado"]]),
          ],
        });
        return { status: 200, body: { reserva: actual, compra: compra() } };
      },
    });
    abrir();
    const r = await tarjeta("Reserva H4N8WQ");
    await userEvent.click(await r.findByRole("checkbox", { name: /Tomás Gómez, 18E/ }));

    await userEvent.click(r.getByRole("button", { name: /Pagar 2 viajeros/ }));

    expect(await r.findByText(/Laura Gómez, 18C \(pagado\)/)).toBeVisible();
    expect(r.getAllByRole("checkbox")).toHaveLength(1);
    expect(r.getByRole("button", { name: /Pagar 1 viajero/ })).toBeVisible();
    expect(r.getByText("1 de 1 seleccionados")).toBeVisible();
  });

  it("HU-27: una reserva vencida no ofrece pagar y dice cuándo venció", async () => {
    responderApi({
      [MIS_VIAJES]: ok([VENCIDA]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();

    const r = await tarjeta("Reserva B3M9TA");
    expect(await r.findByText("Vencida el 01/04/2027 09:02.")).toBeVisible();
    expect(r.getByText("Vencida")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Pagar/ })).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("una reserva cancelada tampoco ofrece pagar", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva({ estado: "cancelada", vence_en: null })]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();

    expect(await screen.findByText("Cancelada.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Pagar/ })).toBeNull();
  });

  it("HU-27: reserva_no_vigente se informa y la lista se actualiza", async () => {
    let actual = reserva();
    responderApi({
      [MIS_VIAJES]: () => ok([actual]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [PAGAR]: () => {
        actual = reserva({
          estado: "vencida",
          vence_en: "2027-04-01T14:02:00Z",
          total_pendiente: 0,
        });
        return error(
          409,
          "reserva_no_vigente",
          "La reserva ya no está vigente: venció, se canceló o ya está pagada.",
        );
      },
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: /Pagar 3 viajeros/ }));

    expect(await screen.findByText(/La reserva ya no está vigente/)).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Pagar/ })).toBeNull());
    expect(screen.getByText("Vencida")).toBeVisible();
  });

  it("HU-27: con saldo insuficiente ofrece recargar lo que falta y volver a Mis viajes", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva()]),
      [MONEDERO]: { status: 200, body: { saldo: 500_000 } },
    });
    abrir();

    expect(await screen.findByText(/Te faltan \$ 287\.500/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Recargar $ 287.500" })).toHaveAttribute(
      "href",
      "/monedero/recargar?faltante=287500&codigo=H4N8WQ&volver=%2Fmis-viajes%3Ftipo%3Dreserva%26pagar%3D41",
    );
    expect(screen.getByRole("button", { name: /Pagar 3 viajeros/ })).toBeDisabled();
  });

  it("al volver de recargar con ?pagar la reserva queda marcada y lista para pagar", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva(), VENCIDA]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir("/mis-viajes?tipo=reserva&pagar=41");

    const r = await tarjeta("Reserva H4N8WQ");
    expect(await r.findByText("RES H4N8WQ")).toBeVisible();
    expect(r.getByRole("article")).toHaveClass("sta-pass--selected");
    expect(r.getByRole("button", { name: /Pagar 3 viajeros/ })).toBeEnabled();
  });

  it("HU-35: el menor_sin_adulto del servidor se muestra con el texto del contrato", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva()]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [PAGAR]: error(
        422,
        "menor_sin_adulto",
        "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.",
        {
          viajero_ids: "Paga también a un adulto: un menor no puede quedar solo en la compra.",
        },
      ),
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: /Pagar 3 viajeros/ }));

    expect(
      await screen.findByText(
        "Paga también a un adulto: un menor no puede quedar solo en la compra.",
      ),
    ).toBeVisible();
  });

  it("HU-02: sin el correo verificado avisa y ofrece reenviar la verificación", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva()]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
      [PAGAR]: error(403, "correo_no_verificado", "Verifica tu correo para reservar o comprar."),
    });
    abrir();

    await userEvent.click(await screen.findByRole("button", { name: /Pagar 3 viajeros/ }));

    expect(await screen.findByText("Verifica tu correo para reservar o comprar.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Reenviar la verificación" })).toBeVisible();
  });

  it("filtra por estado y por mes: manda el primer y el último día del mes", async () => {
    responderApi({
      [MIS_VIAJES]: ok([reserva()]),
      [MONEDERO]: { status: 200, body: { saldo: 1_000_000 } },
    });
    abrir();
    await screen.findByText("RES H4N8WQ");

    await userEvent.click(screen.getByRole("button", { name: "Vigentes" }));
    await waitFor(() => expect(ultima().get("estado")).toBe("vigente"));
    await userEvent.selectOptions(screen.getByLabelText("Mes de salida"), "2027-02");

    await waitFor(() => expect(ultima().get("desde")).toBe("2027-02-01"));
    expect(ultima().get("hasta")).toBe("2027-02-28");
    expect(ultima().get("estado")).toBe("vigente");
  });

  it("un trayecto completo muestra los dos tramos bajo un solo código", async () => {
    responderApi({
      [MIS_VIAJES]: ok([
        reserva({
          total: 3_400_000,
          total_pendiente: 3_400_000,
          tramos: [{ vuelo: VUELO_101 }, { vuelo: VUELO_132 }],
          viajeros: [
            viajero(4101, "Laura", "Gómez", [
              [0, "12A", 1_650_000, "reservado"],
              [1, "9C", 1_750_000, "reservado"],
            ]),
          ],
        }),
      ]),
      [MONEDERO]: { status: 200, body: { saldo: 5_000_000 } },
    });
    abrir();

    const r = await tarjeta("Reserva H4N8WQ");
    expect(await r.findByText("RES H4N8WQ")).toBeVisible();
    expect(r.getByText("STA-00132")).toBeVisible();
    expect(r.getByText("$ 3.400.000", { selector: ".sta-pass__price" })).toBeVisible();
    expect(r.getByText(/Laura Gómez, 12A y 9C/)).toBeVisible();
    expect(r.getAllByRole("article")).toHaveLength(2);
  });

  it("sin reservas invita a buscar vuelos; con filtros, a quitarlos", async () => {
    responderApi({
      [MIS_VIAJES]: (url: URL) => ok(url.searchParams.get("estado") ? [] : []),
      [MONEDERO]: { status: 200, body: { saldo: 0 } },
    });
    abrir();

    expect(await screen.findByText("Todavía no tienes reservas")).toBeVisible();
    expect(screen.getByRole("link", { name: "Buscar vuelos" })).toHaveAttribute("href", "/buscar");

    await userEvent.click(screen.getByRole("button", { name: "Vencidas" }));
    expect(await screen.findByText("No hay reservas con estos filtros")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Quitar filtros" }));
    expect(await screen.findByText("Todavía no tienes reservas")).toBeVisible();
  });
});
