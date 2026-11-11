import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schemas } from "@/api/client";
import { AppLayout } from "@/layouts/app-layout";
import { CompletarRegistroPage } from "@/pages/completar-registro";
import { ADMIN, responderApi, SIN_SESION } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  {
    element: <AppLayout />,
    children: [
      { path: "/completar-registro", element: <CompletarRegistroPage /> },
      { path: "/admin", element: <p>Inicio del administrador</p> },
      { path: "/login", element: <p>Pantalla de inicio de sesión</p> },
    ],
  },
];

const VALIDAR = "POST /api/v1/administradores/invitacion/validar";
const COMPLETAR = "POST /api/v1/administradores/invitacion/completar";
const TOKEN = "token-de-jorge";
const MENSAJE_INVALIDO = "El enlace no es válido o venció. Pide al root una invitación nueva.";

const INVITACION: Schemas["InvitacionSalida"] = {
  nombre_usuario: "jtorres",
  email: "jorge.torres@avianco.test",
  expira_en: "2099-12-31T23:59:00Z",
};

const COMPLETO: Schemas["UsuarioSalida"] = {
  ...ADMIN,
  id: 5,
  nombre_usuario: "jtorres",
  email: "jorge.torres@avianco.test",
  nombres: "Jorge",
  apellidos: "Torres",
};

const PERFIL: Schemas["PerfilSalida"] = {
  id: 5,
  nombre_usuario: "jtorres",
  rol: "admin",
  tipo_documento: "CC",
  numero_documento: "10234567",
  nombres: "Jorge",
  apellidos: "Torres",
  fecha_nacimiento: "1990-05-02",
  lugar_nacimiento: "Cali, Valle del Cauca",
  direccion_facturacion: "Cl. 5 # 38-14, Cali",
  genero: "masculino",
  email: "jorge.torres@avianco.test",
  email_verificado: true,
  email_pendiente: null,
  telefono: null,
  imagen_url: null,
  suscrito_noticias: false,
};

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

async function llenarFormulario() {
  const user = userEvent.setup();
  const datos: Record<string, string> = {
    "Número de documento": "10234567",
    Nombres: "Jorge",
    Apellidos: "Torres",
    "Fecha de nacimiento": "1990-05-02",
    "Lugar de nacimiento": "Cali, Valle del Cauca",
    "Dirección de facturación": "Cl. 5 # 38-14, Cali",
    Contraseña: "MiClave2026",
    "Repite la contraseña": "MiClave2026",
  };
  await user.selectOptions(await screen.findByLabelText("Género"), "masculino");
  for (const [etiqueta, valor] of Object.entries(datos)) {
    await user.clear(screen.getByLabelText(etiqueta));
    await user.type(screen.getByLabelText(etiqueta), valor);
  }
  return user;
}

describe("HU-12 · Completar el registro de administrador", () => {
  it("sin token muestra el mensaje de enlace inválido y no llama a la API", async () => {
    responderApi({ "GET /api/v1/auth/me": SIN_SESION });
    renderRutas(rutas, "/completar-registro");

    expect(await screen.findByText(MENSAJE_INVALIDO)).toBeVisible();
    expect(screen.getByRole("link", { name: "Ir a iniciar sesión" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(peticiones(VALIDAR)).toHaveLength(0);
  });

  it("un token vencido o usado muestra el mensaje exacto de la HU", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      [VALIDAR]: {
        status: 400,
        body: {
          error: {
            codigo: "enlace_invalido",
            mensaje: MENSAJE_INVALIDO,
          },
        },
      },
    });
    renderRutas(rutas, "/completar-registro?token=vencido");

    expect(await screen.findByText(MENSAJE_INVALIDO)).toBeVisible();
    expect(peticiones(VALIDAR)).toHaveLength(1);
  });

  it("con un token válido muestra el usuario y el correo de la invitación", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      [VALIDAR]: { status: 200, body: INVITACION },
    });
    renderRutas(rutas, `/completar-registro?token=${TOKEN}`);

    expect((await screen.findAllByText("jorge.torres@avianco.test")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("jtorres").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Contraseña")).toBeVisible();
    expect(screen.getByLabelText("Repite la contraseña")).toBeVisible();
    expect(screen.queryByLabelText("Correo")).not.toBeInTheDocument();
  });

  it("completa el registro con el token, sin enviar el correo, y abre la sesión", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      [VALIDAR]: { status: 200, body: INVITACION },
      [COMPLETAR]: { status: 200, body: COMPLETO },
      "GET /api/v1/usuarios/me/perfil": { status: 200, body: PERFIL },
    });
    renderRutas(rutas, `/completar-registro?token=${TOKEN}`);
    const user = await llenarFormulario();

    await user.click(screen.getByRole("button", { name: "Guardar y entrar" }));

    expect(await screen.findByText("Inicio del administrador")).toBeVisible();
    const cuerpo = (await peticiones(COMPLETAR)[0].json()) as Record<string, unknown>;
    expect(cuerpo).toMatchObject({
      token: TOKEN,
      nombres: "Jorge",
      apellidos: "Torres",
      numero_documento: "10234567",
      contrasena: "MiClave2026",
      confirmacion: "MiClave2026",
      telefono: null,
    });
    expect(cuerpo.email).toBeUndefined();
    expect(cuerpo.contrasena_temporal).toBeUndefined();
  });

  it("si el enlace deja de servir al guardar, muestra el mensaje de la HU", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      [VALIDAR]: { status: 200, body: INVITACION },
      [COMPLETAR]: {
        status: 400,
        body: { error: { codigo: "enlace_invalido", mensaje: MENSAJE_INVALIDO } },
      },
    });
    renderRutas(rutas, `/completar-registro?token=${TOKEN}`);
    const user = await llenarFormulario();

    await user.click(screen.getByRole("button", { name: "Guardar y entrar" }));

    expect(await screen.findByText(MENSAJE_INVALIDO)).toBeVisible();
  });

  it("muestra junto al campo los datos personales rechazados por el servidor", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      [VALIDAR]: { status: 200, body: INVITACION },
      [COMPLETAR]: {
        status: 409,
        body: {
          error: {
            codigo: "datos_duplicados",
            mensaje: "Ya existe una cuenta con estos datos.",
            campos: { numero_documento: "Ya existe un administrador con este documento." },
          },
        },
      },
    });
    renderRutas(rutas, `/completar-registro?token=${TOKEN}`);
    const user = await llenarFormulario();

    await user.click(screen.getByRole("button", { name: "Guardar y entrar" }));

    expect(
      await screen.findByText("Ya existe un administrador con este documento."),
    ).toBeVisible();
    expect(screen.queryByText("Inicio del administrador")).not.toBeInTheDocument();
  });

  it("no envía si las contraseñas no coinciden", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      [VALIDAR]: { status: 200, body: INVITACION },
    });
    renderRutas(rutas, `/completar-registro?token=${TOKEN}`);
    const user = await llenarFormulario();
    await user.clear(screen.getByLabelText("Repite la contraseña"));
    await user.type(screen.getByLabelText("Repite la contraseña"), "OtraClave99");

    await user.click(screen.getByRole("button", { name: "Guardar y entrar" }));

    expect(await screen.findByText("No coincide con la contraseña.")).toBeVisible();
    await waitFor(() => expect(peticiones(COMPLETAR)).toHaveLength(0));
  });
});
