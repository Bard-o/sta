import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequireRole, SoloVisitantes } from "@/auth/require-role";
import { LoginPage } from "@/pages/login";
import { responderApi, ROOT, SIN_SESION } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  { element: <SoloVisitantes />, children: [{ path: "/login", element: <LoginPage /> }] },
  {
    element: <RequireRole roles={["root"]} />,
    children: [{ path: "/root", element: <p>Inicio del root</p> }],
  },
  {
    element: <RequireRole roles={["admin"]} />,
    children: [{ path: "/admin", element: <p>Inicio del administrador</p> }],
  },
];

async function llenarYEnviar(usuario: string, contrasena: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Usuario o correo"), usuario);
  await user.type(screen.getByLabelText("Contraseña"), contrasena);
  await user.click(screen.getByRole("button", { name: "Iniciar sesión" }));
}

describe("Inicio de sesión (HU-03)", () => {
  it("muestra el error de cada campo vacío junto al campo", async () => {
    responderApi({ "GET /api/v1/auth/me": SIN_SESION });
    renderRutas(rutas, "/login");

    await userEvent.click(await screen.findByRole("button", { name: "Iniciar sesión" }));

    expect(await screen.findByText("Escribe tu nombre de usuario o tu correo.")).toBeVisible();
    expect(screen.getByText("Escribe tu contraseña.")).toBeVisible();
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("aria-invalid", "true");
  });

  it("con credenciales incorrectas muestra el mensaje del servidor", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "POST /api/v1/auth/login": {
        status: 401,
        body: {
          error: { codigo: "credenciales_invalidas", mensaje: "Usuario o contraseña incorrectos." },
        },
      },
    });
    renderRutas(rutas, "/login");

    await llenarYEnviar("root", "Otra12345");

    expect(await screen.findByRole("alert")).toHaveTextContent("Usuario o contraseña incorrectos.");
  });

  it("con credenciales correctas entra a la página de inicio de su rol", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "POST /api/v1/auth/login": { status: 200, body: ROOT },
    });
    const { router } = renderRutas(rutas, "/login");

    await llenarYEnviar("root", "Clave1234");

    expect(await screen.findByText("Inicio del root")).toBeVisible();
    expect(router.state.location.pathname).toBe("/root");
  });
});

describe("Rutas protegidas por rol (RF-11)", () => {
  it("sin sesión lleva al login y recuerda a dónde iba", async () => {
    responderApi({ "GET /api/v1/auth/me": SIN_SESION });
    const { router } = renderRutas(rutas, "/admin");

    expect(await screen.findByRole("heading", { name: "Inicia sesión" })).toBeVisible();
    expect(router.state.location.search).toBe("?next=%2Fadmin");
  });

  it("con otro rol lleva a la página de inicio de su rol", async () => {
    responderApi({ "GET /api/v1/auth/me": { status: 200, body: ROOT } });
    const { router } = renderRutas(rutas, "/admin");

    expect(await screen.findByText("Inicio del root")).toBeVisible();
    expect(router.state.location.pathname).toBe("/root");
  });
});
