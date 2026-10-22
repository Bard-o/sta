import { useQuery } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, unwrap } from "@/api/client";
import { RequireRole, SoloVisitantes } from "@/auth/require-role";
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

/** Hace una petición protegida, como cualquier pantalla de un cliente con sesión. */
function PantallaCliente() {
  const perfil = useQuery({
    queryKey: ["perfil"],
    queryFn: () => unwrap(api.GET("/api/v1/usuarios/me/perfil")),
  });
  return <p>{perfil.isError ? "Falló la petición" : "Inicio del cliente"}</p>;
}

const rutas = [
  { element: <SoloVisitantes />, children: [{ path: "/login", element: <LoginPage /> }] },
  {
    element: <RequireRole roles={["root"]} />,
    children: [{ path: "/root", element: <p>Inicio del root</p> }],
  },
  {
    element: <RequireRole roles={["admin"]} />,
    children: [
      { path: "/admin", element: <p>Inicio del administrador</p> },
      { path: "/admin/primer-ingreso", element: <p>Primer ingreso del administrador</p> },
    ],
  },
  {
    element: <RequireRole roles={["cliente"]} />,
    children: [{ path: "/cliente", element: <PantallaCliente /> }],
  },
];

async function llenarYEnviar(usuario: string, contrasena: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Usuario o correo"), usuario);
  await user.type(screen.getByLabelText("Contraseña"), contrasena);
  await user.click(screen.getByRole("button", { name: "Iniciar sesión" }));
}

const loginRechazado = (status: number, codigo: string, mensaje: string) => ({
  "GET /api/v1/auth/me": SIN_SESION,
  "POST /api/v1/auth/login": { status, body: { error: { codigo, mensaje } } },
});

describe("Inicio de sesión (HU-03)", () => {
  it("muestra el error de cada campo vacío junto al campo", async () => {
    responderApi({ "GET /api/v1/auth/me": SIN_SESION });
    renderRutas(rutas, "/login");

    await userEvent.click(await screen.findByRole("button", { name: "Iniciar sesión" }));

    expect(await screen.findByText("Escribe tu nombre de usuario o tu correo.")).toBeVisible();
    expect(screen.getByText("Escribe tu contraseña.")).toBeVisible();
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("aria-invalid", "true");
  });

  // HU-03: con credenciales correctas entra a la página de inicio de su rol.
  it.each([
    ["root", ROOT, "Inicio del root", "/root"],
    ["administrador", ADMIN, "Inicio del administrador", "/admin"],
    ["cliente", CLIENTE, "Inicio del cliente", "/cliente"],
  ])("con credenciales correctas el %s entra a su inicio", async (_rol, usuario, texto, ruta) => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "POST /api/v1/auth/login": sesionDe(usuario),
      "GET /api/v1/usuarios/me/perfil": { status: 200, body: {} },
    });
    const { router } = renderRutas(rutas, "/login");

    await llenarYEnviar("usuario", "Clave1234");

    expect(await screen.findByText(texto)).toBeVisible();
    expect(router.state.location.pathname).toBe(ruta);
  });

  it("vuelve a la ruta que el usuario quería abrir (?next=)", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "POST /api/v1/auth/login": sesionDe(ROOT),
    });
    const { router } = renderRutas(rutas, "/login?next=%2Froot");

    await llenarYEnviar("root", "Clave1234");

    expect(await screen.findByText("Inicio del root")).toBeVisible();
    expect(router.state.location.pathname).toBe("/root");
  });

  // HU-12: el administrador con el registro incompleto entra siempre a S07.
  it("lleva al administrador con el registro incompleto al primer ingreso", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "POST /api/v1/auth/login": sesionDe(ADMIN_INCOMPLETO),
    });
    const { router } = renderRutas(rutas, "/login?next=%2Fadmin");

    await llenarYEnviar("jtorres", "Temporal123");

    expect(await screen.findByText("Primer ingreso del administrador")).toBeVisible();
    expect(router.state.location.pathname).toBe("/admin/primer-ingreso");
  });

  // HU-03: el mensaje no revela cuál de los dos datos falló.
  it("con credenciales incorrectas muestra un mensaje genérico y no marca ningún campo", async () => {
    responderApi(
      loginRechazado(401, "credenciales_invalidas", "Usuario o contraseña incorrectos."),
    );
    renderRutas(rutas, "/login");

    await llenarYEnviar("root", "Otra12345");

    expect(await screen.findByRole("alert")).toHaveTextContent("Usuario o contraseña incorrectos.");
    expect(screen.getByLabelText("Usuario o correo")).not.toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Contraseña")).not.toHaveAttribute("aria-invalid", "true");
  });

  // HU-03 / RNF-13: tras 5 intentos fallidos se rechaza aunque la clave sea correcta y se avisa la espera.
  it("con la cuenta bloqueada informa el tiempo de espera", async () => {
    responderApi(
      loginRechazado(
        429,
        "demasiados_intentos",
        "Cuenta bloqueada. Intenta de nuevo en 15 minutos.",
      ),
    );
    renderRutas(rutas, "/login");

    await llenarYEnviar("bloqueado", "Clave1234");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cuenta bloqueada. Intenta de nuevo en 15 minutos.",
    );
    expect(screen.getByRole("heading", { name: "Inicia sesión" })).toBeVisible();
  });

  // HU-03: una cuenta desactivada recibe «cuenta inactiva».
  it("con una cuenta desactivada muestra «cuenta inactiva»", async () => {
    responderApi(loginRechazado(403, "cuenta_inactiva", "Cuenta inactiva."));
    renderRutas(rutas, "/login");

    await llenarYEnviar("amejia", "Clave1234");

    expect(await screen.findByRole("alert")).toHaveTextContent("Cuenta inactiva.");
  });

  it("si no hay conexión con el servidor muestra un mensaje y no se queda cargando", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "POST /api/v1/auth/login": { status: 500, body: {} },
    });
    renderRutas(rutas, "/login");

    await llenarYEnviar("root", "Clave1234");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No pudimos comunicarnos con el servidor. Intenta de nuevo.",
    );
    expect(screen.getByRole("button", { name: "Iniciar sesión" })).toBeEnabled();
  });
});

describe("Sesión vencida por inactividad (HU-03, RNF-14)", () => {
  it("la siguiente acción pide iniciar sesión otra vez y lo avisa", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(CLIENTE),
      "GET /api/v1/usuarios/me/perfil": SIN_SESION,
    });
    const { router } = renderRutas(rutas, "/cliente");

    expect(await screen.findByRole("heading", { name: "Inicia sesión" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Tu sesión venció por inactividad. Inicia sesión de nuevo.",
    );
    expect(router.state.location.search).toBe("?next=%2Fcliente");
  });

  it("un visitante no ve el aviso de sesión vencida", async () => {
    responderApi({ "GET /api/v1/auth/me": SIN_SESION });
    renderRutas(rutas, "/login");

    expect(await screen.findByRole("heading", { name: "Inicia sesión" })).toBeVisible();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("un error de credenciales de un visitante no se confunde con una sesión vencida", async () => {
    responderApi(
      loginRechazado(401, "credenciales_invalidas", "Usuario o contraseña incorrectos."),
    );
    renderRutas(rutas, "/login");

    await llenarYEnviar("root", "Otra12345");

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.queryByText(/venció por inactividad/)).not.toBeInTheDocument();
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
    responderApi({ "GET /api/v1/auth/me": sesionDe(ROOT) });
    const { router } = renderRutas(rutas, "/admin");

    expect(await screen.findByText("Inicio del root")).toBeVisible();
    expect(router.state.location.pathname).toBe("/root");
  });
});
