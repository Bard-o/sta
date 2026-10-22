import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EditarVueloPage } from "@/pages/editar-vuelo";
import { ADMIN, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";
import { BOG, ciudad, conReservas, MDE, PEI, resumenCiudad, vueloAdmin } from "@/test/vuelos";

const rutas = [
  { path: "/admin/vuelos/:vueloId/editar", element: <EditarVueloPage /> },
  { path: "/admin/vuelos", element: <p>Vuelos programados</p> },
];

const SESION = "GET /api/v1/auth/me";
const CIUDADES = "GET /api/v1/ciudades";
const GESTION_31 = "GET /api/v1/vuelos/31/gestion";
const GUARDAR_31 = "PUT /api/v1/vuelos/31";
const VISTA = "POST /api/v1/vuelos/vista-previa";

const NUEVA_VISTA = {
  status: 200,
  body: {
    tipo: "nacional",
    origen: resumenCiudad(PEI),
    destino: resumenCiudad(BOG),
    salida: "2026-12-10T12:00:00Z",
    llegada: "2026-12-10T12:50:00Z",
    duracion_minutos: 50,
    capacidad: { primera: 25, economica: 125, total: 150 },
  },
};

const servidor = (extra: Record<string, unknown> = {}) =>
  responderApi({
    [SESION]: sesionDe(ADMIN),
    [CIUDADES]: { status: 200, body: [PEI, BOG, MDE, ciudad("CLO", "Cali")] },
    [GESTION_31]: { status: 200, body: vueloAdmin() },
    [GUARDAR_31]: { status: 200, body: vueloAdmin({ precio_economica: 300000 }) },
    [VISTA]: NUEVA_VISTA,
    ...extra,
  } as Parameters<typeof responderApi>[0]);

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

/** El formulario arranca cuando llegan el vuelo y el catálogo de ciudades. */
async function abrir() {
  renderRutas(rutas, "/admin/vuelos/31/editar");
  await screen.findByRole("heading", { name: "Editar vuelo STA-00031" });
  await screen.findAllByRole("option", { name: "Cali (CLO)" });
}

describe("S09 · Editar vuelo (HU-15)", () => {
  it("abre el formulario con los datos del vuelo en la hora local del origen", async () => {
    servidor();
    await abrir();

    expect(screen.getByLabelText("Origen", { exact: true })).toHaveValue("PEI");
    expect(screen.getByLabelText("Destino", { exact: true })).toHaveValue("BOG");
    expect(screen.getByLabelText("Fecha de salida")).toHaveValue("2026-12-10");
    expect(screen.getByLabelText(/^Hora de salida/)).toHaveValue("06:00");
    expect(screen.getByLabelText("Horas")).toHaveValue("0");
    expect(screen.getByLabelText("Minutos")).toHaveValue("50");
    expect(screen.getByLabelText("Precio por persona, económica")).toHaveValue("$ 280.000");
    expect(screen.getByLabelText("Precio por persona, primera")).toHaveValue("$ 750.000");
  });

  it("muestra el pase con el código real y no pide vista previa si no cambia la salida", async () => {
    servidor();
    await abrir();

    expect(await screen.findByText("STA-00031")).toBeVisible();
    expect(screen.getByText(/Llegada calculada:/).parentElement).toHaveTextContent(
      "10/12/2026 06:50 en Bogotá (UTC-5)",
    );
    expect(peticiones(VISTA)).toHaveLength(0);
  });

  it("guarda el cambio de precio y vuelve a la lista", async () => {
    servidor();
    await abrir();
    const user = userEvent.setup();

    const precio = screen.getByLabelText("Precio por persona, económica");
    await user.clear(precio);
    await user.type(precio, "300000");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("Vuelos programados")).toBeVisible();
    expect(await peticiones(GUARDAR_31)[0].json()).toEqual({
      origen: "PEI",
      destino: "BOG",
      fecha_salida: "2026-12-10",
      hora_salida: "06:00",
      duracion_minutos: 50,
      precio_economica: 300000,
      precio_primera: 750000,
    });
  });

  it("si cambia la hora, pide la vista previa para recalcular la llegada", async () => {
    servidor();
    await abrir();
    const user = userEvent.setup();

    const hora = screen.getByLabelText(/^Hora de salida/);
    await user.clear(hora);
    await user.type(hora, "07:00");

    await waitFor(() => expect(peticiones(VISTA)).toHaveLength(1), { timeout: 3000 });
    expect((await peticiones(VISTA)[0].json()).hora_salida).toBe("07:00");
    expect(await screen.findByText(/Llegada calculada:/)).toBeVisible();
  });

  it("vuelve a aplicar las validaciones de HU-13 (destino igual al origen)", async () => {
    servidor();
    await abrir();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Destino", { exact: true }), "PEI");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("El destino debe ser distinto del origen.")).toBeVisible();
    expect(peticiones(GUARDAR_31)).toHaveLength(0);
  });

  it("un choque con otro vuelo se muestra junto a la hora de salida", async () => {
    servidor({
      [GUARDAR_31]: {
        status: 409,
        body: {
          error: {
            codigo: "vuelo_duplicado",
            mensaje: "Ya existe un vuelo de esta ruta a esa hora.",
            campos: { hora_salida: "Ya existe un vuelo de esta ruta a esa hora." },
          },
        },
      },
    });
    await abrir();
    const user = userEvent.setup();

    const precio = screen.getByLabelText("Precio por persona, económica");
    await user.clear(precio);
    await user.type(precio, "300000");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(screen.getByLabelText(/^Hora de salida/)).toBeInvalid());
  });

  it("si mientras tanto el vuelo vendió algo, el servidor lo rechaza y se explica", async () => {
    servidor({
      [GUARDAR_31]: {
        status: 409,
        body: {
          error: {
            codigo: "vuelo_con_reservas",
            mensaje: "El vuelo tiene reservas activas o compras y no se puede editar.",
          },
        },
      },
    });
    await abrir();
    const user = userEvent.setup();

    const precio = screen.getByLabelText("Precio por persona, económica");
    await user.clear(precio);
    await user.type(precio, "300000");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText(/no se puede editar/)).toBeVisible();
  });

  it("un vuelo con reservas activas se bloquea e indica el motivo", async () => {
    servidor({ "GET /api/v1/vuelos/51/gestion": { status: 200, body: conReservas() } });
    renderRutas(rutas, "/admin/vuelos/51/editar");

    expect(await screen.findByText(/Este vuelo no se puede editar\./)).toBeVisible();
    expect(screen.getByText(/Tiene 2 reservas activas\./)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Guardar cambios" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a vuelos programados" })).toBeVisible();
  });

  it("un vuelo realizado o cancelado tampoco se edita", async () => {
    servidor({
      "GET /api/v1/vuelos/31/gestion": {
        status: 200,
        body: vueloAdmin({
          estado: "cancelado",
          editable: false,
          motivo_no_editable: "El vuelo ya se realizó o está cancelado.",
        }),
      },
    });
    renderRutas(rutas, "/admin/vuelos/31/editar");

    expect(await screen.findByText(/El vuelo ya se realizó o está cancelado\./)).toBeVisible();
    expect(screen.queryByLabelText("Origen", { exact: true })).not.toBeInTheDocument();
  });

  it("un vuelo que no existe muestra «Página no encontrada»", async () => {
    servidor({
      "GET /api/v1/vuelos/999/gestion": {
        status: 404,
        body: { error: { codigo: "no_encontrado", mensaje: "El vuelo no existe." } },
      },
    });
    renderRutas(rutas, "/admin/vuelos/999/editar");

    expect(await screen.findByText("Página no encontrada")).toBeVisible();
  });

  it("una dirección con un identificador inválido no consulta nada", async () => {
    servidor();
    renderRutas(rutas, "/admin/vuelos/abc/editar");

    expect(await screen.findByText("Página no encontrada")).toBeVisible();
    expect(peticiones("GET /api/v1/vuelos/NaN/gestion")).toHaveLength(0);
  });
});
