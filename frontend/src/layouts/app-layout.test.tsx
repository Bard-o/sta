import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequireRole, SoloVisitantes } from "@/auth/require-role";
import { AppLayout } from "@/layouts/app-layout";
import { LoginPage } from "@/pages/login";
import {
  ADMIN,
  ADMIN_INCOMPLETO,
  CLIENTE,
  responderApi,
  ROOT,
  SIN_SESION,
  sesionDe,
} from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <h1>Inicio público</h1> },
      { path: "/verificar-correo", element: <p>Verificación de correo</p> },
      { element: <SoloVisitantes />, children: [{ path: "/login", element: <LoginPage /> }] },
      {
        element: <RequireRole roles={["cliente"]} />,
        children: [{ path: "/cliente", element: <p>Inicio del cliente</p> }],
      },
      {
        element: <RequireRole roles={["admin"]} />,
        children: [
          { path: "/admin", element: <p>Inicio del administrador</p> },
          { path: "/admin/primer-ingreso", element: <p>Primer ingreso del administrador</p> },
        ],
      },
      {
        element: <RequireRole roles={["root"]} />,
        children: [{ path: "/root", element: <p>Inicio del root</p> }],
      },
    ],
  },
];

describe("Cerrar sesión (HU-04)", () => {
  // HU-04: «Disponible en cualquier momento desde el menú del rol».
  it.each([
    ["cliente", CLIENTE, "/cliente"],
    ["administrador", ADMIN, "/admin"],
    ["root", ROOT, "/root"],
  ])("el %s cierra sesión y ve la página pública de inicio", async (_rol, usuario, inicio) => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(usuario),
      "POST /api/v1/auth/logout": { status: 204 },
    });
    const { router } = renderRutas(rutas, inicio);

    await userEvent.click(await screen.findByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { name: "Inicio público" })).toBeVisible();
    expect(router.state.location.pathname).toBe("/");
    expect(screen.queryByRole("button", { name: "Cerrar sesión" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toBeVisible();
  });

  it("invalida la sesión en el servidor, no solo en el navegador", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(CLIENTE),
      "POST /api/v1/auth/logout": { status: 204 },
    });
    renderRutas(rutas, "/cliente");

    await userEvent.click(await screen.findByRole("button", { name: "Cerrar sesión" }));
    await screen.findByRole("heading", { name: "Inicio público" });

    const llamadas = vi.mocked(fetch).mock.calls.map(([peticion]) => {
      const req = peticion as Request;
      return `${req.method} ${new URL(req.url).pathname}`;
    });
    expect(llamadas).toContain("POST /api/v1/auth/logout");
  });

  // HU-04: una petición posterior con la sesión anterior es rechazada y pide iniciar sesión.
  it("después de cerrar sesión, las rutas protegidas piden iniciar sesión", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(CLIENTE),
      "POST /api/v1/auth/logout": { status: 204 },
    });
    const { router } = renderRutas(rutas, "/cliente");
    await userEvent.click(await screen.findByRole("button", { name: "Cerrar sesión" }));
    await screen.findByRole("heading", { name: "Inicio público" });

    // El servidor ya no reconoce la sesión anterior.
    responderApi({ "GET /api/v1/auth/me": SIN_SESION });
    await router.navigate("/cliente");

    expect(await screen.findByRole("heading", { name: "Inicia sesión" })).toBeVisible();
    expect(screen.queryByText("Inicio del cliente")).not.toBeInTheDocument();
  });

  it("si el servidor falla al cerrar sesión, conserva la sesión y no navega", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(CLIENTE),
      "POST /api/v1/auth/logout": {
        status: 500,
        body: { error: { codigo: "error_interno", mensaje: "Algo salió mal." } },
      },
    });
    const { router } = renderRutas(rutas, "/cliente");

    await userEvent.click(await screen.findByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("button", { name: "Cerrar sesión" })).toBeEnabled();
    expect(router.state.location.pathname).toBe("/cliente");
    expect(screen.getByText("Inicio del cliente")).toBeVisible();
  });
});

describe("Menú de cada rol (HU-03)", () => {
  it("muestra nombres y apellidos de quien tiene sesión", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(CLIENTE) });
    renderRutas(rutas, "/cliente");

    const menu = await screen.findByRole("banner");
    expect(await within(menu).findByText("Laura Gómez Ríos")).toBeVisible();
    expect(within(menu).getByText("Cliente")).toBeVisible();
  });

  it("muestra el nombre de usuario si no hay nombres (root)", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ROOT) });
    renderRutas(rutas, "/root");

    const menu = await screen.findByRole("banner");
    expect(await within(menu).findByText("root")).toBeVisible();
    expect(within(menu).getByText("Root")).toBeVisible();
  });

  it("no muestra el menú de visitante mientras se resuelve la sesión", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(CLIENTE) });
    renderRutas(rutas, "/cliente");

    // Primer pintado: la sesión aún no responde.
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).queryByRole("link", { name: "Check-in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Iniciar sesión" })).not.toBeInTheDocument();

    expect(await within(nav).findByRole("link", { name: "Mis viajes" })).toBeVisible();
  });

  it("cada rol ve solo los items de su menú", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN) });
    renderRutas(rutas, "/admin");

    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(await within(nav).findByRole("link", { name: "Vuelos programados" })).toBeVisible();
    expect(within(nav).queryByRole("link", { name: "Monedero" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Check-in" })).not.toBeInTheDocument();
  });

  // HU-12: con el registro incompleto el administrador solo ve el formulario de registro.
  it("lleva al administrador con el registro incompleto a su primer ingreso desde cualquier ruta", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO) });
    const { router } = renderRutas(rutas, "/");

    expect(await screen.findByText("Primer ingreso del administrador")).toBeVisible();
    expect(router.state.location.pathname).toBe("/admin/primer-ingreso");

    await router.navigate("/admin");
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/primer-ingreso"));
    expect(await screen.findByText("Primer ingreso del administrador")).toBeVisible();
  });

  it("el administrador con el registro incompleto no ve el menú de funciones, pero puede cerrar sesión", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO) });
    renderRutas(rutas, "/admin/primer-ingreso");

    expect(await screen.findByRole("button", { name: "Cerrar sesión" })).toBeVisible();
    expect(screen.getByText("jtorres")).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).queryAllByRole("link")).toHaveLength(0);
  });
});

describe("Aviso de correo sin verificar (HU-02)", () => {
  it("el cliente con el correo sin verificar ve el aviso con el enlace a la verificación", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe({ ...CLIENTE, email_verificado: false }) });
    renderRutas(rutas, "/cliente");

    expect(await screen.findByText(/Verifica tu correo para reservar, comprar/)).toBeVisible();
    await userEvent.click(screen.getByRole("link", { name: "Verificar correo" }));
    expect(await screen.findByText("Verificación de correo")).toBeVisible();
    expect(screen.queryByText(/Verifica tu correo para reservar, comprar/)).not.toBeInTheDocument();
  });

  it.each([
    ["cliente verificado", CLIENTE],
    ["administrador", { ...ADMIN, email_verificado: false }],
  ])("no lo ve el %s", async (_nombre, usuario) => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(usuario) });
    renderRutas(rutas, usuario.rol === "admin" ? "/admin" : "/cliente");

    await screen.findByRole("button", { name: "Cerrar sesión" });
    expect(screen.queryByText(/Verifica tu correo para reservar, comprar/)).not.toBeInTheDocument();
  });
});
