import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequireRole, SoloRegistroPendiente } from "@/auth/require-role";
import { AppLayout } from "@/layouts/app-layout";
import { PrimerIngresoPage } from "@/pages/primer-ingreso";
import { ADMIN, ADMIN_INCOMPLETO, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

const RUTA = "/admin/primer-ingreso";

const rutas = [
  {
    element: <AppLayout />,
    children: [
      {
        element: <RequireRole roles={["admin"]} />,
        children: [
          {
            element: <SoloRegistroPendiente />,
            children: [{ path: RUTA, element: <PrimerIngresoPage /> }],
          },
          { path: "/admin", element: <p>Inicio del administrador</p> },
        ],
      },
    ],
  },
];

/** Respuesta del servidor cuando el registro queda completo. */
const COMPLETADO = {
  ...ADMIN_INCOMPLETO,
  email: "jorge.torres@avianco.test",
  email_verificado: true,
  registro_completo: true,
  nombres: "Jorge",
  apellidos: "Torres",
};

async function llenarFormulario(user: ReturnType<typeof userEvent.setup>) {
  // La ruta espera a que responda la sesión antes de pintar el formulario.
  await screen.findByRole("heading", { name: "Tus datos de administrador" });
  await user.selectOptions(screen.getByLabelText("Tipo de documento"), "CC");
  await user.type(screen.getByLabelText("Número de documento"), "10234567");
  await user.selectOptions(screen.getByLabelText("Género"), "masculino");
  await user.type(screen.getByLabelText("Nombres"), "Jorge");
  await user.type(screen.getByLabelText("Apellidos"), "Torres");
  fireEvent.change(screen.getByLabelText("Fecha de nacimiento"), {
    target: { value: "1990-05-02" },
  });
  await user.type(screen.getByLabelText("Lugar de nacimiento"), "Cali, Valle del Cauca");
  await user.type(screen.getByLabelText("Dirección de facturación"), "Cl. 5 # 38-14, Cali");
  await user.type(screen.getByLabelText("Correo"), "jorge.torres@avianco.test");
  await user.type(screen.getByLabelText("Contraseña temporal"), "Temporal123");
  await user.type(screen.getByLabelText("Contraseña nueva"), "MiClave2026");
  await user.type(screen.getByLabelText("Repite la nueva"), "MiClave2026");
  await user.click(screen.getByRole("button", { name: "Guardar y entrar" }));
}

const errorApi = (status: number, codigo: string, mensaje: string, campos?: object) => ({
  status,
  body: { error: campos ? { codigo, mensaje, campos } : { codigo, mensaje } },
});

describe("Primer ingreso del administrador (HU-12)", () => {
  it("muestra el formulario de S07 con el aviso de completar el registro", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO) });
    renderRutas(rutas, RUTA);

    expect(
      await screen.findByRole("heading", { name: "Tus datos de administrador" }),
    ).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Completa tu registro para continuar. El menú se habilita cuando termines.",
    );
    expect(screen.getByRole("button", { name: "Guardar y entrar" })).toBeEnabled();
    expect(screen.getByLabelText("Contraseña temporal")).toBeVisible();
  });

  // HU-12: al completarlo se muestra el menú de administrador y se entra a su inicio.
  it("envía los datos, actualiza la sesión y entra al inicio del administrador", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO),
      "POST /api/v1/administradores/me/registro": { status: 200, body: COMPLETADO },
    });
    const user = userEvent.setup();
    const { router } = renderRutas(rutas, RUTA);

    await llenarFormulario(user);

    expect(await screen.findByText("Inicio del administrador")).toBeVisible();
    expect(router.state.location.pathname).toBe("/admin");
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(await within(nav).findByRole("link", { name: "Vuelos programados" })).toBeVisible();
    expect(within(screen.getByRole("banner")).getByText("Jorge Torres")).toBeVisible();

    // El cuerpo sigue el contrato: sin teléfono en el wireframe, sin nombre de usuario ni política.
    const peticion = vi
      .mocked(fetch)
      .mock.calls.map(([entrada]) => entrada as Request)
      .find((req) => req.method === "POST");
    expect(await peticion!.json()).toMatchObject({
      tipo_documento: "CC",
      numero_documento: "10234567",
      nombres: "Jorge",
      apellidos: "Torres",
      fecha_nacimiento: "1990-05-02",
      lugar_nacimiento: "Cali, Valle del Cauca",
      direccion_facturacion: "Cl. 5 # 38-14, Cali",
      genero: "masculino",
      email: "jorge.torres@avianco.test",
      telefono: null,
      contrasena_temporal: "Temporal123",
    });
  });

  it("no llama a la API si faltan datos y marca cada campo", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO) });
    renderRutas(rutas, RUTA);

    await userEvent.click(await screen.findByRole("button", { name: "Guardar y entrar" }));

    expect(await screen.findByText("Escribe tus nombres.")).toBeVisible();
    expect(screen.getByText("Escribe tus apellidos.")).toBeVisible();
    expect(screen.getByText("Elige tu fecha de nacimiento.")).toBeVisible();
    expect(screen.getByText("Elige tu género.")).toBeVisible();
    expect(screen.getByText("Escribe un correo válido.")).toBeVisible();
    expect(screen.getByText("Escribe la contraseña temporal.")).toBeVisible();
    expect(screen.getByLabelText("Nombres")).toHaveAttribute("aria-invalid", "true");

    const metodos = vi.mocked(fetch).mock.calls.map(([entrada]) => (entrada as Request).method);
    expect(metodos).not.toContain("POST");
  });

  it("rechaza una fecha de nacimiento futura antes de enviar", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO) });
    const user = userEvent.setup();
    renderRutas(rutas, RUTA);

    await llenarFormulario(user);
    fireEvent.change(screen.getByLabelText("Fecha de nacimiento"), {
      target: { value: "2999-01-01" },
    });
    await user.click(screen.getByRole("button", { name: "Guardar y entrar" }));

    expect(await screen.findByText("La fecha de nacimiento no puede ser futura.")).toBeVisible();
  });

  it("avisa si la confirmación no coincide con la contraseña nueva", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO) });
    const user = userEvent.setup();
    renderRutas(rutas, RUTA);

    await llenarFormulario(user);
    await user.clear(screen.getByLabelText("Repite la nueva"));
    await user.type(screen.getByLabelText("Repite la nueva"), "OtraClave2026");
    await user.click(screen.getByRole("button", { name: "Guardar y entrar" }));

    expect(await screen.findByText("No coincide con la contraseña nueva.")).toBeVisible();
  });

  // HU-12: contraseña temporal errada → error junto al campo (422 contrasena_actual_incorrecta).
  it("muestra junto al campo la contraseña temporal incorrecta", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO),
      "POST /api/v1/administradores/me/registro": errorApi(
        422,
        "contrasena_actual_incorrecta",
        "La contraseña temporal no es correcta.",
        { contrasena_temporal: "La contraseña temporal no es correcta." },
      ),
    });
    const user = userEvent.setup();
    renderRutas(rutas, RUTA);

    await llenarFormulario(user);

    expect(await screen.findByText("La contraseña temporal no es correcta.")).toBeVisible();
    expect(screen.getByLabelText("Contraseña temporal")).toHaveAttribute("aria-invalid", "true");
  });

  // HU-12: la política de contraseña se valida también en el servidor (RNF-08).
  it("muestra junto al campo el error de política de la contraseña nueva", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO),
      "POST /api/v1/administradores/me/registro": errorApi(
        422,
        "datos_invalidos",
        "Revisa los campos marcados.",
        { contrasena_nueva: "Debe tener al menos 8 caracteres, con letras y números." },
      ),
    });
    const user = userEvent.setup();
    renderRutas(rutas, RUTA);

    await llenarFormulario(user);

    expect(
      await screen.findByText("Debe tener al menos 8 caracteres, con letras y números."),
    ).toBeVisible();
    expect(screen.getByLabelText("Contraseña nueva")).toHaveAttribute("aria-invalid", "true");
  });

  // RF-04: documento y correo únicos entre administradores → datos_duplicados.
  it("marca el documento y el correo que ya pertenecen a otro administrador", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO),
      "POST /api/v1/administradores/me/registro": errorApi(
        409,
        "datos_duplicados",
        "Ya existe una cuenta con estos datos.",
        {
          numero_documento: "Ya existe una cuenta con este documento.",
          email: "Ya existe una cuenta con este correo.",
        },
      ),
    });
    const user = userEvent.setup();
    renderRutas(rutas, RUTA);

    await llenarFormulario(user);

    expect(await screen.findByText("Ya existe una cuenta con este documento.")).toBeVisible();
    expect(screen.getByText("Ya existe una cuenta con este correo.")).toBeVisible();
  });

  // HU-12: 409 registro_ya_completo se avisa como error general.
  it("avisa si el registro ya estaba completo", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(ADMIN_INCOMPLETO),
      "POST /api/v1/administradores/me/registro": errorApi(
        409,
        "registro_ya_completo",
        "Tu registro ya está completo.",
      ),
    });
    const user = userEvent.setup();
    renderRutas(rutas, RUTA);

    await llenarFormulario(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Tu registro ya está completo.");
  });

  // HU-12: un administrador que ya completó su registro no ve S07.
  it("lleva al administrador con el registro completo al inicio de su rol", async () => {
    responderApi({ "GET /api/v1/auth/me": sesionDe(ADMIN) });
    const { router } = renderRutas(rutas, RUTA);

    expect(await screen.findByText("Inicio del administrador")).toBeVisible();
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin"));
    expect(screen.queryByRole("button", { name: "Guardar y entrar" })).not.toBeInTheDocument();
  });
});
