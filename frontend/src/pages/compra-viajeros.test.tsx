import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schemas } from "@/api/client";
import type { SeleccionCarrito } from "@/auth/carrito";
import { CompraViajerosPage } from "@/pages/compra-viajeros";
import { CLIENTE, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

type Tramo = SeleccionCarrito["tramos"][number];
type Vuelo = Tramo["vuelo"];
type Detalle = Schemas["VueloDetalle"];

const rutas = [
  { path: "/compra/viajeros", element: <CompraViajerosPage /> },
  { path: "/compra/pago/:compraId", element: <p>Pago con monedero</p> },
  { path: "/mis-viajes", element: <p>Mis viajes</p> },
  { path: "/carrito", element: <p>Tu carrito</p> },
  { path: "/verificar-correo", element: <p>Verificar correo</p> },
];

const BOGOTA = "America/Bogota";
const NUEVA_YORK = "America/New_York";
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
  llegada: "2027-04-22T18:20:00Z",
  duracion_minutos: 320,
};

const tramo = (vuelo: Vuelo, precio = 262_500, clase: Tramo["clase"] = "economica"): Tramo => ({
  vuelo,
  clase,
  precio_unitario: precio,
  precio_al_agregar: precio,
  promocion_porcentaje: null,
  disponibles: 12,
  tiquetes_activos: 0,
});

const seleccion = (tramos: Tramo[], cambios: Partial<SeleccionCarrito> = {}): SeleccionCarrito => ({
  id: 71,
  tramos,
  viajeros: 1,
  subtotal: tramos.reduce((s, t) => s + t.precio_unitario, 0),
  confirmable: true,
  avisos: [],
  reserva_venceria_en: "2027-04-14T11:00:00Z",
  agregada_en: "2026-11-17T10:00:00Z",
  ...cambios,
});

const clase = (precio: number, disponibles = 10) => ({
  precio_base: precio,
  precio_vigente: precio,
  promocion: null,
  disponibles,
  agotada: disponibles === 0,
});

const detalle = (vuelo: Vuelo, economica: number, primera: number): Detalle => ({
  ...vuelo,
  precio_economica: economica,
  precio_primera: primera,
  capacidad: { primera: 25, economica: 125, total: 150 },
  economica: clase(economica),
  primera: clase(primera),
});

const PERFIL = {
  id: 12,
  nombre_usuario: "lauragomez",
  rol: "cliente",
  tipo_documento: "CC",
  numero_documento: "1088345921",
  nombres: "Laura",
  apellidos: "Gómez Ríos",
  fecha_nacimiento: "1995-03-14",
  genero: "femenino",
  email: "laura.gomez@correo.co",
  telefono: "310 555 0192",
};

const VIAJE = { id: 901, codigo: "K7Q2PX", tipo: "reserva", estado: "vigente" };

const CARRITO = "GET /api/v1/carrito";
const RESERVAR = "POST /api/v1/reservas";
const COMPRAR = "POST /api/v1/compras";
const QUITAR = "DELETE /api/v1/carrito/selecciones/71";

const carritoCon = (...selecciones: SeleccionCarrito[]) => ({
  status: 200,
  body: { selecciones, cantidad: selecciones.length, total: 0 },
});
const error = (
  status: number,
  codigo: string,
  mensaje: string,
  campos?: Record<string, string>,
) => ({
  status,
  body: { error: { codigo, mensaje, campos } },
});

const SIMPLE = seleccion([tramo(VUELO_131)]);
const COMPLETA = seleccion([tramo(VUELO_101, 1_650_000), tramo(VUELO_132, 1_750_000)]);

const base = (extra: Record<string, unknown> = {}) => ({
  "GET /api/v1/auth/me": sesionDe(CLIENTE),
  "GET /api/v1/usuarios/me/perfil": { status: 200, body: PERFIL },
  [CARRITO]: carritoCon(SIMPLE),
  "GET /api/v1/vuelos/131": { status: 200, body: detalle(VUELO_131, 262_500, 690_000) },
  "GET /api/v1/vuelos/101": { status: 200, body: detalle(VUELO_101, 1_650_000, 4_100_000) },
  "GET /api/v1/vuelos/132": { status: 200, body: detalle(VUELO_132, 1_750_000, 3_900_000) },
  ...extra,
});

const llamadas = (metodo: string, ruta: string) =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => r.method === metodo && new URL(r.url).pathname === ruta);

const viajero = (n: number) => within(screen.getByRole("group", { name: `Viajero ${n}` }));

const DATOS = {
  "Número de documento": "1088999000",
  Nombres: "Daniel",
  Apellidos: "Arango",
  "Fecha de nacimiento": "1990-08-15",
  Teléfono: "311 555 0188",
  Correo: "daniel.arango@correo.co",
  "Contacto de emergencia": "Laura Gómez",
  "Teléfono del contacto": "310 555 0192",
};

async function llenar(n: number, datos: Record<string, string> = DATOS) {
  const tarjeta = viajero(n);
  for (const [etiqueta, valor] of Object.entries(datos)) {
    await userEvent.type(tarjeta.getByLabelText(etiqueta), valor);
  }
  await userEvent.selectOptions(tarjeta.getByLabelText("Género"), "masculino");
}

const abrir = (url = "/compra/viajeros?seleccion=71") => renderRutas(rutas, url);

describe("S17 · Datos de los viajeros y reservar o comprar (HU-24, HU-25, HU-26)", () => {
  it("muestra el paso Viajeros, el vuelo y un formulario por viajero", async () => {
    responderApi(base({ [CARRITO]: carritoCon({ ...SIMPLE, viajeros: 2 }) }));
    abrir();

    expect(await screen.findByRole("heading", { name: "¿Quiénes viajan?" })).toBeVisible();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Viajeros");
    expect(screen.getByText(/STA-00131, Pereira → Bogotá, 15\/04\/2027 06:00/)).toBeVisible();
    expect(screen.getByRole("group", { name: "Viajero 1" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Viajero 2" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Reservar 2 tiquetes" })).toBeVisible();
  });

  it("RF-31: «Soy yo» llena los datos del viajero desde el perfil", async () => {
    responderApi(base());
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });

    await waitFor(() => expect(viajero(1).getByRole("button", { name: /Soy yo/ })).toBeEnabled());
    await userEvent.click(viajero(1).getByRole("button", { name: /Soy yo/ }));

    const v = viajero(1);
    expect(v.getByLabelText("Número de documento")).toHaveValue("1088345921");
    expect(v.getByLabelText("Nombres")).toHaveValue("Laura");
    expect(v.getByLabelText("Apellidos")).toHaveValue("Gómez Ríos");
    expect(v.getByLabelText("Fecha de nacimiento")).toHaveValue("1995-03-14");
    expect(v.getByLabelText("Género")).toHaveValue("femenino");
    expect(v.getByLabelText("Correo")).toHaveValue("laura.gomez@correo.co");
    expect(v.getByLabelText("Teléfono")).toHaveValue("310 555 0192");
  });

  it("HU-24: la fecha de nacimiento muestra la edad que tendrá el viajero el día del vuelo", async () => {
    responderApi(base());
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });

    await userEvent.type(viajero(1).getByLabelText("Fecha de nacimiento"), "2012-05-02");

    expect(viajero(1).getByText("Tendrá 14 años el día del vuelo.")).toBeVisible();
  });

  it("HU-24: un único viajero menor se advierte antes de enviar", async () => {
    responderApi(base());
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    expect(screen.queryByText(/debe viajar con al menos un adulto/)).toBeNull();

    await userEvent.type(viajero(1).getByLabelText("Fecha de nacimiento"), "2012-05-02");

    expect(
      await screen.findByText(/Un menor de edad debe viajar con al menos un adulto/),
    ).toBeVisible();
  });

  it("IU-07: cada campo vacío se marca en el viajero que corresponde y no se envía nada", async () => {
    responderApi(base({ [CARRITO]: carritoCon({ ...SIMPLE, viajeros: 2 }) }));
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    await llenar(1);

    await userEvent.click(screen.getByRole("button", { name: "Reservar 2 tiquetes" }));

    expect(await viajero(2).findByText("Escribe los nombres del viajero.")).toBeVisible();
    expect(viajero(2).getByText("Escribe el teléfono del viajero.")).toBeVisible();
    expect(viajero(1).queryByText("Escribe los nombres del viajero.")).toBeNull();
    expect(llamadas("POST", "/api/v1/reservas")).toHaveLength(0);
  });

  it("HU-24: reservar envía el viaje, muestra hasta cuándo se congela y lleva a Mis viajes", async () => {
    responderApi(base({ [RESERVAR]: { status: 201, body: VIAJE }, [QUITAR]: { status: 204 } }));
    const { router } = abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    expect(
      screen.getByText(/hasta el 14\/04\/2027 a las 06:00 \(hora de Colombia\)/),
    ).toBeVisible();
    await llenar(1);

    await userEvent.click(screen.getByRole("button", { name: "Reservar 1 tiquete" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/mis-viajes"));
    expect(router.state.location.search).toBe("?tipo=reserva");
    expect(await llamadas("POST", "/api/v1/reservas")[0].clone().json()).toEqual({
      tramos: [{ vuelo_id: 131 }],
      viajeros: [
        {
          tipo_documento: "CC",
          numero_documento: "1088999000",
          nombres: "Daniel",
          apellidos: "Arango",
          fecha_nacimiento: "1990-08-15",
          genero: "masculino",
          telefono: "311 555 0188",
          email: "daniel.arango@correo.co",
          contacto_nombre: "Laura Gómez",
          contacto_telefono: "310 555 0192",
          clases: ["economica"],
        },
      ],
    });
    // La selección sale del carrito después de reservar.
    await waitFor(() =>
      expect(llamadas("DELETE", "/api/v1/carrito/selecciones/71")).toHaveLength(1),
    );
  });

  it("HU-25: comprar inicia la compra y lleva al pago con la selección, sin quitarla todavía", async () => {
    responderApi(
      base({ [COMPRAR]: { status: 201, body: { ...VIAJE, tipo: "compra", estado: "pendiente" } } }),
    );
    const { router } = abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    await userEvent.click(screen.getByRole("radio", { name: /Comprar ahora/ }));
    await llenar(1);

    await userEvent.click(screen.getByRole("button", { name: "Comprar 1 tiquete" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/compra/pago/901"));
    expect(router.state.location.search).toBe("?seleccion=71");
    expect(llamadas("DELETE", "/api/v1/carrito/selecciones/71")).toHaveLength(0);
    expect(llamadas("POST", "/api/v1/reservas")).toHaveLength(0);
  });

  it("HU-24: un documento con tiquete activo marca ese campo con el mensaje del contrato", async () => {
    responderApi(
      base({
        [RESERVAR]: error(
          409,
          "viajero_duplicado",
          "Uno de los documentos ya tiene un tiquete activo en este vuelo.",
          {
            "viajeros.0.numero_documento":
              "Este documento ya tiene un tiquete activo en este vuelo.",
          },
        ),
      }),
    );
    const { router } = abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    await llenar(1);

    await userEvent.click(screen.getByRole("button", { name: "Reservar 1 tiquete" }));

    expect(
      await viajero(1).findByText("Este documento ya tiene un tiquete activo en este vuelo."),
    ).toBeVisible();
    expect(viajero(1).getByLabelText("Número de documento")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(router.state.location.pathname).toBe("/compra/viajeros");
  });

  it("HU-24: el menor_sin_adulto del servidor se muestra en cada menor", async () => {
    responderApi(
      base({
        [RESERVAR]: error(
          422,
          "menor_sin_adulto",
          "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.",
          {
            "viajeros.0.fecha_nacimiento":
              "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.",
          },
        ),
      }),
    );
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    await llenar(1, { ...DATOS, "Fecha de nacimiento": "2012-05-02" });

    await userEvent.click(screen.getByRole("button", { name: "Reservar 1 tiquete" }));

    expect(
      await viajero(1).findByText(/Un menor de edad debe viajar con al menos un adulto/),
    ).toBeVisible();
  });

  it("RF-42: clase_agotada y limite_tiquetes se informan sin perder lo escrito", async () => {
    responderApi(
      base({
        [RESERVAR]: error(409, "clase_agotada", "No quedan sillas suficientes en esta clase."),
      }),
    );
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    await llenar(1);

    await userEvent.click(screen.getByRole("button", { name: "Reservar 1 tiquete" }));

    expect(await screen.findByText("No quedan sillas suficientes en esta clase.")).toBeVisible();
    expect(viajero(1).getByLabelText("Nombres")).toHaveValue("Daniel");
  });

  it("HU-02: sin el correo verificado avisa y ofrece reenviar la verificación", async () => {
    responderApi(
      base({
        [RESERVAR]: error(
          403,
          "correo_no_verificado",
          "Verifica tu correo para reservar o comprar.",
        ),
      }),
    );
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    await llenar(1);

    await userEvent.click(screen.getByRole("button", { name: "Reservar 1 tiquete" }));

    expect(await screen.findByText("Verifica tu correo para reservar o comprar.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Reenviar la verificación" })).toHaveAttribute(
      "href",
      "/verificar-correo",
    );
  });

  it("HU-26: en un trayecto completo los viajeros se llenan una vez y la clase se elige en cada tramo", async () => {
    responderApi(
      base({
        [CARRITO]: carritoCon(COMPLETA),
        [COMPRAR]: { status: 201, body: { ...VIAJE, tipo: "compra", estado: "pendiente" } },
      }),
    );
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    expect(
      screen.getByText(/STA-00101 y STA-00132, Pereira → Nueva York → Cartagena/),
    ).toBeVisible();
    // Una sola tarjeta de viajero con una clase por tramo.
    expect(screen.getAllByRole("group", { name: /Viajero/ })).toHaveLength(1);
    const v = viajero(1);
    await userEvent.selectOptions(v.getByLabelText("Clase del regreso"), "primera");
    expect(screen.getByText("$ 5.550.000", { selector: ".price" })).toBeVisible();
    await userEvent.click(screen.getByRole("radio", { name: /Comprar ahora/ }));
    await llenar(1);

    expect(screen.getByRole("button", { name: "Comprar 2 tiquetes" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Comprar 2 tiquetes" }));

    await waitFor(() => expect(llamadas("POST", "/api/v1/compras")).toHaveLength(1));
    const cuerpo = (await llamadas("POST", "/api/v1/compras")[0].clone().json()) as {
      tramos: unknown;
      viajeros: { clases: string[] }[];
    };
    expect(cuerpo.tramos).toEqual([{ vuelo_id: 101 }, { vuelo_id: 132 }]);
    expect(cuerpo.viajeros).toHaveLength(1);
    expect(cuerpo.viajeros[0].clases).toEqual(["economica", "primera"]);
  });

  it("el total sigue la clase elegida de cada viajero con los precios de hoy", async () => {
    responderApi(base());
    abrir();
    await screen.findByRole("group", { name: "Viajero 1" });
    expect(screen.getByText("$ 262.500", { selector: ".price" })).toBeVisible();

    await waitFor(() =>
      expect(
        within(viajero(1).getByLabelText("Clase")).getByRole("option", {
          name: /Primera clase, \$ 690\.000/,
        }),
      ).toBeVisible(),
    );
    await userEvent.selectOptions(viajero(1).getByLabelText("Clase"), "primera");

    expect(screen.getByText("$ 690.000", { selector: ".price" })).toBeVisible();
  });

  it("una selección que ya no está en el carrito lo dice y vuelve al carrito", async () => {
    responderApi(base({ [CARRITO]: carritoCon() }));
    abrir();

    expect(await screen.findByText(/Esa selección ya no está en tu carrito/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Volver al carrito" })).toHaveAttribute(
      "href",
      "/carrito",
    );
  });

  it("sin ?seleccion no hay nada que reservar", async () => {
    responderApi(base());
    abrir("/compra/viajeros");

    expect(await screen.findByText(/Esa selección ya no está en tu carrito/)).toBeVisible();
  });
});
