import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequireRole, SoloVisitantes } from "@/auth/require-role";
import type { Schemas } from "@/api/client";
import { PerfilPage } from "@/pages/perfil";
import { ADMIN, CLIENTE, responderApi, SIN_SESION, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  { path: "/", element: <h1>Inicio público</h1> },
  { element: <SoloVisitantes />, children: [{ path: "/login", element: <p>Inicio de sesión</p> }] },
  {
    element: <RequireRole roles={["cliente", "admin", "root"]} />,
    children: [{ path: "/perfil", element: <PerfilPage /> }],
  },
];

const PERFIL: Schemas["PerfilSalida"] = {
  id: 12,
  nombre_usuario: "lauragomez",
  rol: "cliente",
  tipo_documento: "CC",
  numero_documento: "1088345921",
  nombres: "Laura",
  apellidos: "Gómez Ríos",
  fecha_nacimiento: "1995-03-14",
  lugar_nacimiento: "Pereira, Risaralda",
  direccion_facturacion: "Cra. 7 # 19-28, Pereira",
  genero: "femenino",
  email: "laura.gomez@correo.co",
  email_verificado: true,
  email_pendiente: null,
  telefono: null,
  imagen_url: null,
  suscrito_noticias: false,
};

const SESION = "GET /api/v1/auth/me";
const ESTADO = "GET /api/v1/usuarios/me/desactivacion";
const DESACTIVAR = "POST /api/v1/usuarios/me/desactivacion";

const LIBRE = { status: 200, body: { puede_desactivar: true, bloqueos: [] } };
const BLOQUEADA = {
  status: 200,
  body: {
    puede_desactivar: false,
    bloqueos: [
      {
        tipo: "compra",
        codigo_reserva: "K7Q2MX",
        vuelo_id: 88,
        vuelo_codigo: "STA-00088",
        origen: "Bogotá",
        destino: "Madrid",
        salida: "2026-12-11T03:00:00Z",
      },
    ],
  },
};

const base = (estado: typeof LIBRE | typeof BLOQUEADA) => ({
  [SESION]: sesionDe(CLIENTE),
  "GET /api/v1/usuarios/me/perfil": { status: 200, body: PERFIL },
  [ESTADO]: estado,
});

const peticiones = (llave: string) =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);

const botonDesactivar = () => screen.findByRole("button", { name: "Desactivar cuenta" });

describe("S05 · Desactivar cuenta (HU-09)", () => {
  it("pide confirmación y advierte que no se podrá volver a iniciar sesión", async () => {
    responderApi(base(LIBRE));
    renderRutas(rutas, "/perfil");

    await userEvent.click(await botonDesactivar());

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("¿Desactivar tu cuenta?")).toBeVisible();
    expect(within(dialogo).getByText(/No podrás volver a iniciar sesión/)).toBeVisible();
    expect(peticiones(DESACTIVAR)).toHaveLength(0);
  });

  it("«Volver» cierra el diálogo sin desactivar", async () => {
    responderApi(base(LIBRE));
    renderRutas(rutas, "/perfil");

    await userEvent.click(await botonDesactivar());
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Volver" }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(peticiones(DESACTIVAR)).toHaveLength(0);
  });

  it("tras confirmar, cierra la sesión y lleva a la página pública", async () => {
    responderApi({ ...base(LIBRE), [DESACTIVAR]: { status: 204 } });
    const { router } = renderRutas(rutas, "/perfil");

    await userEvent.click(await botonDesactivar());
    const dialogo = await screen.findByRole("dialog");
    await userEvent.click(within(dialogo).getByRole("button", { name: "Desactivar cuenta" }));

    expect(await screen.findByRole("heading", { name: "Inicio público" })).toBeVisible();
    expect(router.state.location.pathname).toBe("/");
    expect(peticiones(DESACTIVAR)).toHaveLength(1);
  });

  it("después, las rutas protegidas piden iniciar sesión", async () => {
    responderApi({ ...base(LIBRE), [DESACTIVAR]: { status: 204 } });
    const { router, queryClient } = renderRutas(rutas, "/perfil");

    await userEvent.click(await botonDesactivar());
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Desactivar cuenta" }),
    );
    await screen.findByRole("heading", { name: "Inicio público" });

    expect(queryClient.getQueryData(["sesion"])).toBeNull();
    responderApi({ [SESION]: SIN_SESION });
    await router.navigate("/perfil");
    expect(await screen.findByText("Inicio de sesión")).toBeVisible();
  });

  it("con compras o reservas activas deshabilita el botón y lista cuáles", async () => {
    responderApi(base(BLOQUEADA));
    renderRutas(rutas, "/perfil");

    expect(await botonDesactivar()).toBeDisabled();
    expect(
      await screen.findByText(
        "Compra K7Q2MX: vuelo STA-00088, Bogotá → Madrid, sale el 10/12/2026.",
      ),
    ).toBeVisible();
    expect(screen.getByText(/cancela estas compras o reservas/)).toBeVisible();
  });

  it("si el servidor rechaza por tiquetes activos, muestra el motivo y no cierra la sesión", async () => {
    responderApi({
      ...base(LIBRE),
      [DESACTIVAR]: {
        status: 409,
        body: {
          error: {
            codigo: "tiquetes_activos",
            mensaje: "Tienes compras o reservas activas en vuelos futuros.",
          },
        },
      },
    });
    renderRutas(rutas, "/perfil");

    await userEvent.click(await botonDesactivar());
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Desactivar cuenta" }),
    );

    expect(
      await screen.findByText("Tienes compras o reservas activas en vuelos futuros."),
    ).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: "Inicio público" })).not.toBeInTheDocument();
  });

  it("el administrador no ve la desactivación (es solo del cliente)", async () => {
    responderApi({
      [SESION]: sesionDe(ADMIN),
      "GET /api/v1/usuarios/me/perfil": { status: 200, body: { ...PERFIL, rol: "admin" } },
    });
    renderRutas(rutas, "/perfil");

    await screen.findByLabelText("Nombres");
    expect(screen.queryByRole("button", { name: "Desactivar cuenta" })).not.toBeInTheDocument();
    expect(peticiones(ESTADO)).toHaveLength(0);
  });
});
