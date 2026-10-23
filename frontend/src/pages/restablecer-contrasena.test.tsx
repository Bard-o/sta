import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SESION_KEY } from "@/auth/sesion";
import { RestablecerContrasenaPage } from "@/pages/restablecer-contrasena";
import { CLIENTE, responderApi } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  { path: "/restablecer-contrasena", element: <RestablecerContrasenaPage /> },
  { path: "/login", element: <p>Pantalla de inicio de sesión</p> },
];

const SOLICITAR = "POST /api/v1/auth/restablecimiento";
const CONFIRMAR = "POST /api/v1/auth/restablecimiento/confirmar";
const MENSAJE = "Si el correo está registrado, recibirás un enlace válido por 30 minutos.";

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

describe("S04 · Paso 1: pedir el enlace (HU-05)", () => {
  it("muestra el mismo mensaje exista o no el correo", async () => {
    responderApi({ [SOLICITAR]: { status: 202, body: { mensaje: MENSAJE } } });
    renderRutas(rutas, "/restablecer-contrasena");
    const user = userEvent.setup();
    const correo = await screen.findByLabelText("Correo de la cuenta");

    await user.type(correo, "laura.gomez@correo.co");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));
    expect(await screen.findByText(MENSAJE)).toBeVisible();

    await user.clear(correo);
    await user.type(correo, "no.existe@correo.co");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));
    expect(await screen.findAllByText(MENSAJE)).toHaveLength(1);
    expect(peticiones(SOLICITAR)).toHaveLength(2);
    expect(await peticiones(SOLICITAR)[1].json()).toEqual({ email: "no.existe@correo.co" });
  });

  it("no envía nada con un correo mal formado y lo indica junto al campo", async () => {
    responderApi({});
    renderRutas(rutas, "/restablecer-contrasena");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Correo de la cuenta"), "laura.gomez");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));

    expect(await screen.findByText(/Escribe un correo válido/)).toBeVisible();
    expect(peticiones(SOLICITAR)).toHaveLength(0);
  });

  it("si el servidor falla, lo dice sin mostrar el mensaje de éxito", async () => {
    responderApi({
      [SOLICITAR]: {
        status: 500,
        body: { error: { codigo: "error_interno", mensaje: "Algo salió mal. Intenta de nuevo." } },
      },
    });
    renderRutas(rutas, "/restablecer-contrasena");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Correo de la cuenta"), "laura.gomez@correo.co");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));

    expect(await screen.findByText("Algo salió mal. Intenta de nuevo.")).toBeVisible();
    expect(screen.queryByText(MENSAJE)).not.toBeInTheDocument();
  });

  it("vuelve al inicio de sesión", async () => {
    responderApi({});
    renderRutas(rutas, "/restablecer-contrasena");
    await userEvent.click(await screen.findByRole("link", { name: "Volver a iniciar sesión" }));
    expect(await screen.findByText("Pantalla de inicio de sesión")).toBeVisible();
  });
});

async function escribirNueva(nueva: string, repetida = nueva) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Contraseña nueva"), nueva);
  await user.type(screen.getByLabelText("Repite la contraseña"), repetida);
  await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));
  return user;
}

describe("S04 · Paso 2: contraseña nueva desde el enlace (HU-05)", () => {
  it("guarda la contraseña nueva y ofrece iniciar sesión", async () => {
    responderApi({ [CONFIRMAR]: { status: 204 } });
    renderRutas(rutas, "/restablecer-contrasena?token=abc123");
    await escribirNueva("OtraClave99");

    expect(await screen.findByText(/inicia sesión con tu contraseña nueva/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
    expect(await peticiones(CONFIRMAR)[0].json()).toEqual({
      token: "abc123",
      contrasena_nueva: "OtraClave99",
      confirmacion: "OtraClave99",
    });
  });

  it("olvida la sesión de este navegador, porque el servidor cerró todas", async () => {
    responderApi({ [CONFIRMAR]: { status: 204 } });
    const { queryClient } = renderRutas(rutas, "/restablecer-contrasena?token=abc123");
    queryClient.setQueryData(SESION_KEY, CLIENTE);
    await escribirNueva("OtraClave99");

    await screen.findByText(/Cerramos tus sesiones abiertas/);
    expect(queryClient.getQueryData(SESION_KEY)).toBeNull();
  });

  it("avisa que se cierran las sesiones de otros dispositivos", async () => {
    responderApi({});
    renderRutas(rutas, "/restablecer-contrasena?token=abc123");
    expect(
      await screen.findByText(
        "Al guardar, cerramos las sesiones abiertas en tus otros dispositivos.",
      ),
    ).toBeVisible();
  });

  it("exige que cumpla la política y que las dos coincidan, junto a cada campo", async () => {
    responderApi({});
    renderRutas(rutas, "/restablecer-contrasena?token=abc123");
    await escribirNueva("abcdefgh", "abcdefgx");

    expect(await screen.findByText("La contraseña debe tener al menos un número.")).toBeVisible();
    expect(peticiones(CONFIRMAR)).toHaveLength(0);
  });

  it("indica cuando no coinciden", async () => {
    responderApi({});
    renderRutas(rutas, "/restablecer-contrasena?token=abc123");
    await escribirNueva("OtraClave99", "OtraClave98");

    expect(await screen.findByText("No coincide con la contraseña nueva.")).toBeVisible();
    expect(peticiones(CONFIRMAR)).toHaveLength(0);
  });

  it("muestra los errores de campo que reporta el servidor", async () => {
    responderApi({
      [CONFIRMAR]: {
        status: 422,
        body: {
          error: {
            codigo: "datos_invalidos",
            mensaje: "Revisa los campos marcados.",
            campos: { contrasena_nueva: "Esa contraseña es demasiado común." },
          },
        },
      },
    });
    renderRutas(rutas, "/restablecer-contrasena?token=abc123");
    await escribirNueva("Clave1234");

    expect(await screen.findByText("Esa contraseña es demasiado común.")).toBeVisible();
    expect(screen.getByLabelText("Contraseña nueva")).toBeInvalid();
  });

  it("un enlace vencido o usado muestra el error y permite pedir otro", async () => {
    responderApi({
      [CONFIRMAR]: {
        status: 400,
        body: { error: { codigo: "enlace_invalido", mensaje: "Enlace inválido." } },
      },
    });
    const { router } = renderRutas(rutas, "/restablecer-contrasena?token=vencido");
    const user = await escribirNueva("OtraClave99");

    expect(await screen.findByText(/Este enlace venció o ya fue usado/)).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Pedir un enlace nuevo" }));

    expect(await screen.findByLabelText("Correo de la cuenta")).toBeVisible();
    expect(router.state.location.search).toBe("");
  });

  it("nunca muestra las contraseñas: los campos son de tipo contraseña", async () => {
    responderApi({});
    renderRutas(rutas, "/restablecer-contrasena?token=abc123");
    expect(await screen.findByLabelText("Contraseña nueva")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Repite la contraseña")).toHaveAttribute("type", "password");
  });
});
