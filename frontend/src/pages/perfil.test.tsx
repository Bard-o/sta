import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequireRole } from "@/auth/require-role";
import type { Schemas } from "@/api/client";
import { PerfilPage } from "@/pages/perfil";
import { ADMIN, CLIENTE, responderApi, ROOT, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  {
    element: <RequireRole roles={["cliente", "admin", "root"]} />,
    children: [{ path: "/perfil", element: <PerfilPage /> }],
  },
  { path: "/login", element: <p>Pantalla de inicio de sesión</p> },
  { path: "/root", element: <p>Inicio del root</p> },
  { path: "/verificar-correo", element: <p>Verificación de correo</p> },
  { path: "/otra", element: <p>Otra pantalla</p> },
];

type Perfil = Schemas["PerfilSalida"];

const PERFIL_LAURA: Perfil = {
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
  telefono: "310 555 0192",
  imagen_url: null,
  suscrito_noticias: false,
};

const SESION = "GET /api/v1/auth/me";
const DESACTIVACION = "GET /api/v1/usuarios/me/desactivacion";
const LIBRE = { status: 200, body: { puede_desactivar: true, bloqueos: [] } };
const PERFIL = "GET /api/v1/usuarios/me/perfil";
const GUARDAR = "PUT /api/v1/usuarios/me/perfil";
const IMAGEN = "PUT /api/v1/usuarios/me/imagen";
const QUITAR = "DELETE /api/v1/usuarios/me/imagen";
const CONTRASENA = "PUT /api/v1/usuarios/me/contrasena";
const SUSCRIPCION = "PUT /api/v1/usuarios/me/suscripcion";

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

/** Servidor con estado: lo que se guarda es lo que devuelve el siguiente GET. */
function servidor(inicial: Perfil = PERFIL_LAURA, usuario = CLIENTE) {
  const estado = { perfil: inicial };
  responderApi({
    [SESION]: sesionDe(usuario),
    [DESACTIVACION]: LIBRE,
    [PERFIL]: () => ({ status: 200, body: estado.perfil }),
    [GUARDAR]: () => ({ status: 200, body: estado.perfil }),
  });
  return estado;
}

const campo = (nombre: string) => screen.findByLabelText(nombre);

describe("S05 · Datos personales (HU-07)", () => {
  it("muestra los datos del perfil y deja el documento y el usuario en solo lectura", async () => {
    servidor();
    renderRutas(rutas, "/perfil");

    expect(await campo("Nombres")).toHaveValue("Laura");
    expect(screen.getByLabelText("Apellidos")).toHaveValue("Gómez Ríos");
    expect(screen.getByLabelText("Teléfono (opcional)")).toHaveValue("310 555 0192");
    expect(screen.getByLabelText("Correo")).toHaveValue("laura.gomez@correo.co");
    for (const [etiqueta, valor] of [
      ["Tipo de documento", "Cédula de ciudadanía"],
      ["Número de documento", "1088345921"],
      ["Usuario", "lauragomez"],
    ]) {
      expect(screen.getByText(etiqueta)).toBeVisible();
      expect(screen.getByText(valor)).toBeVisible();
      expect(screen.queryByLabelText(etiqueta)).not.toBeInTheDocument();
    }
  });

  it("guarda los cambios y, al volver a abrir el perfil, se ven actualizados", async () => {
    const servidorFalso = servidor();
    const { router } = renderRutas(rutas, "/perfil");
    const user = userEvent.setup();

    const nombres = await campo("Nombres");
    await user.clear(nombres);
    await user.type(nombres, "Laura Sofía");
    const telefono = screen.getByLabelText("Teléfono (opcional)");
    await user.clear(telefono);
    servidorFalso.perfil = { ...PERFIL_LAURA, nombres: "Laura Sofía", telefono: null };
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(peticiones(GUARDAR)).toHaveLength(1));
    expect(await peticiones(GUARDAR)[0].json()).toEqual({
      nombres: "Laura Sofía",
      apellidos: "Gómez Ríos",
      fecha_nacimiento: "1995-03-14",
      lugar_nacimiento: "Pereira, Risaralda",
      direccion_facturacion: "Cra. 7 # 19-28, Pereira",
      genero: "femenino",
      email: "laura.gomez@correo.co",
      telefono: null,
    });

    await router.navigate("/otra");
    await screen.findByText("Otra pantalla");
    await router.navigate("/perfil");
    expect(await campo("Nombres")).toHaveValue("Laura Sofía");
  });

  it("al cambiar el correo, el nuevo queda pendiente y el anterior sigue vigente", async () => {
    const servidorFalso = servidor();
    renderRutas(rutas, "/perfil");
    const user = userEvent.setup();

    const correo = await campo("Correo");
    await user.clear(correo);
    await user.type(correo, "laura.g@nuevo.co");
    servidorFalso.perfil = { ...PERFIL_LAURA, email_pendiente: "laura.g@nuevo.co" };
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(
      await screen.findByText(
        /Pendiente de verificar\. Hasta entonces sigue vigente laura\.gomez@correo\.co\./,
      ),
    ).toBeVisible();
    expect(screen.getByLabelText("Correo")).toHaveValue("laura.g@nuevo.co");
    expect((await peticiones(GUARDAR)[0].json()).email).toBe("laura.g@nuevo.co");
    await user.click(screen.getByRole("link", { name: "Reenviar enlace" }));
    expect(await screen.findByText("Verificación de correo")).toBeVisible();
  });

  it("rechaza un correo que ya usa otra cuenta, junto al campo", async () => {
    servidor();
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
      [GUARDAR]: {
        status: 409,
        body: {
          error: {
            codigo: "datos_duplicados",
            mensaje: "Ya existe una cuenta con estos datos.",
            campos: { email: "Ya existe una cuenta con este correo." },
          },
        },
      },
    });
    renderRutas(rutas, "/perfil");
    const user = userEvent.setup();

    const correo = await campo("Correo");
    await user.clear(correo);
    await user.type(correo, "pedro@correo.co");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("Ya existe una cuenta con este correo.")).toBeVisible();
    await waitFor(() => expect(correo).toBeInvalid());
  });

  it("valida en pantalla: fecha futura, correo mal formado y campos vacíos", async () => {
    servidor();
    renderRutas(rutas, "/perfil");
    const user = userEvent.setup();

    const nombres = await campo("Nombres");
    await user.clear(nombres);
    await user.clear(screen.getByLabelText("Fecha de nacimiento"));
    await user.type(screen.getByLabelText("Fecha de nacimiento"), "2999-01-01");
    const correo = screen.getByLabelText("Correo");
    await user.clear(correo);
    await user.type(correo, "laura");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText("Escribe tus nombres.")).toBeVisible();
    expect(screen.getByText("La fecha de nacimiento no puede ser futura.")).toBeVisible();
    expect(screen.getByText(/Escribe un correo válido/)).toBeVisible();
    expect(peticiones(GUARDAR)).toHaveLength(0);
  });

  it("un correo sin verificar ofrece verificarlo", async () => {
    servidor({ ...PERFIL_LAURA, email_verificado: false });
    renderRutas(rutas, "/perfil");

    expect(await screen.findByText(/Tu correo aún no está verificado/)).toBeVisible();
    for (const enlace of screen.getAllByRole("link", { name: "Verificar correo" })) {
      expect(enlace).toHaveAttribute("href", "/verificar-correo");
    }
  });

  it("el administrador también tiene perfil", async () => {
    servidor({ ...PERFIL_LAURA, rol: "admin", nombre_usuario: "cruiz", nombres: "Carlos" }, ADMIN);
    renderRutas(rutas, "/perfil");

    expect(await campo("Nombres")).toHaveValue("Carlos");
  });

  it("el root no tiene perfil: solo ve el cambio de contraseña y no pide el perfil", async () => {
    responderApi({ [SESION]: sesionDe(ROOT) });
    renderRutas(rutas, "/perfil");

    expect(await screen.findByRole("heading", { name: "Mi cuenta" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Cambiar contraseña" })).toBeVisible();
    expect(screen.queryByLabelText("Nombres")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(peticiones(PERFIL)).toHaveLength(0);
  });
});

describe("S05 · Imagen de perfil (HU-07)", () => {
  const png = () => new File(["x"], "laura.png", { type: "image/png" });

  it("sube la imagen al elegirla y muestra la que guardó el servidor", async () => {
    servidor();
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
      [IMAGEN]: {
        status: 200,
        body: { ...PERFIL_LAURA, imagen_url: "/api/v1/usuarios/me/imagen?v=3" },
      },
    });
    renderRutas(rutas, "/perfil");
    const user = userEvent.setup();

    await user.upload(await screen.findByLabelText("Archivo de imagen de perfil"), png());

    const imagen = await screen.findByAltText("Tu imagen de perfil");
    expect(imagen).toHaveAttribute("src", "/api/v1/usuarios/me/imagen?v=3");
    expect(peticiones(IMAGEN)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Cambiar imagen" })).toBeVisible();
  });

  it("no envía un archivo que no es JPG o PNG", async () => {
    servidor();
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
    });
    renderRutas(rutas, "/perfil");
    const entrada = await screen.findByLabelText("Archivo de imagen de perfil");

    // `applyAccept: false` simula a quien arrastra un archivo que el selector filtraría.
    await userEvent
      .setup({ applyAccept: false })
      .upload(entrada, new File(["x"], "foto.gif", { type: "image/gif" }));

    expect(await screen.findByText("La imagen debe ser JPG o PNG.")).toBeVisible();
    expect(peticiones(IMAGEN)).toHaveLength(0);
  });

  it("muestra el error del servidor si rechaza la imagen", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
      [IMAGEN]: {
        status: 422,
        body: {
          error: {
            codigo: "datos_invalidos",
            mensaje: "Revisa los campos marcados.",
            campos: { imagen: "La imagen no es un JPG o PNG válido." },
          },
        },
      },
    });
    renderRutas(rutas, "/perfil");
    await userEvent.upload(await screen.findByLabelText("Archivo de imagen de perfil"), png());

    expect(await screen.findByText("La imagen no es un JPG o PNG válido.")).toBeVisible();
    expect(screen.queryByAltText("Tu imagen de perfil")).not.toBeInTheDocument();
  });

  it("quita la imagen actual", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: {
        status: 200,
        body: { ...PERFIL_LAURA, imagen_url: "/api/v1/usuarios/me/imagen?v=3" },
      },
      [QUITAR]: { status: 204 },
    });
    renderRutas(rutas, "/perfil");
    await screen.findByAltText("Tu imagen de perfil");

    await userEvent.click(screen.getByRole("button", { name: "Quitar" }));

    await waitFor(() =>
      expect(screen.queryByAltText("Tu imagen de perfil")).not.toBeInTheDocument(),
    );
    expect(peticiones(QUITAR)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Quitar" })).not.toBeInTheDocument();
  });
});

async function escribirContrasenas(actual: string, nueva: string, repetida = nueva) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Actual"), actual);
  await user.type(screen.getByLabelText("Nueva"), nueva);
  await user.type(screen.getByLabelText("Repite la nueva"), repetida);
  await user.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
}

describe("S05 · Contraseña (HU-06)", () => {
  it("cambia la contraseña con la actual correcta y limpia los campos", async () => {
    servidor();
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
      [CONTRASENA]: { status: 204 },
    });
    renderRutas(rutas, "/perfil");
    await escribirContrasenas("Clave1234", "OtraClave99");

    await waitFor(() => expect(peticiones(CONTRASENA)).toHaveLength(1));
    expect(await peticiones(CONTRASENA)[0].json()).toEqual({
      contrasena_actual: "Clave1234",
      contrasena_nueva: "OtraClave99",
      confirmacion: "OtraClave99",
    });
    await waitFor(() => expect(screen.getByLabelText("Actual")).toHaveValue(""));
    expect(screen.getByLabelText("Nueva")).toHaveValue("");
  });

  it("si la actual es incorrecta, lo indica junto al campo y no cambia nada", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
      [CONTRASENA]: {
        status: 422,
        body: {
          error: {
            codigo: "contrasena_actual_incorrecta",
            mensaje: "La contraseña actual no es correcta.",
            campos: { contrasena_actual: "La contraseña actual no es correcta." },
          },
        },
      },
    });
    renderRutas(rutas, "/perfil");
    await escribirContrasenas("Equivocada1", "OtraClave99");

    expect(await screen.findByText("La contraseña actual no es correcta.")).toBeVisible();
    expect(screen.getByLabelText("Actual")).toBeInvalid();
    expect(screen.getByLabelText("Nueva")).toHaveValue("OtraClave99");
  });

  it("rechaza una nueva que no cumple la política o no coincide, indicando el motivo", async () => {
    servidor();
    renderRutas(rutas, "/perfil");
    await escribirContrasenas("Clave1234", "sololetras", "otracosa");

    expect(await screen.findByText("La contraseña debe tener al menos un número.")).toBeVisible();
    expect(screen.getByText("No coincide con la contraseña nueva.")).toBeVisible();
    expect(peticiones(CONTRASENA)).toHaveLength(0);
  });

  it("el root cambia su contraseña desde su cuenta", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [CONTRASENA]: { status: 204 } });
    renderRutas(rutas, "/perfil");
    await escribirContrasenas("Clave1234", "OtraClave99");

    await waitFor(() => expect(peticiones(CONTRASENA)).toHaveLength(1));
  });
});

describe("S05 · Correos que recibes (HU-08)", () => {
  it("el cliente se suscribe a las noticias", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
      [SUSCRIPCION]: { status: 200, body: { noticias: true } },
    });
    renderRutas(rutas, "/perfil");
    const interruptor = await screen.findByRole("switch", {
      name: "Noticias de vuelos y promociones",
    });
    expect(interruptor).not.toBeChecked();

    await userEvent.click(interruptor);

    await waitFor(() => expect(interruptor).toBeChecked());
    expect(await peticiones(SUSCRIPCION)[0].json()).toEqual({ noticias: true });
  });

  it("el cliente suscrito se da de baja", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: { ...PERFIL_LAURA, suscrito_noticias: true } },
      [SUSCRIPCION]: { status: 200, body: { noticias: false } },
    });
    renderRutas(rutas, "/perfil");
    const interruptor = await screen.findByRole("switch", {
      name: "Noticias de vuelos y promociones",
    });
    expect(interruptor).toBeChecked();

    await userEvent.click(interruptor);

    await waitFor(() => expect(interruptor).not.toBeChecked());
    expect(await peticiones(SUSCRIPCION)[0].json()).toEqual({ noticias: false });
  });

  it("con el correo sin verificar no se puede suscribir y se ofrece verificarlo", async () => {
    servidor({ ...PERFIL_LAURA, email_verificado: false });
    renderRutas(rutas, "/perfil");

    const interruptor = await screen.findByRole("switch", {
      name: "Noticias de vuelos y promociones",
    });
    expect(interruptor).toBeDisabled();
    expect(screen.getByText(/Verifica tu correo para suscribirte a noticias/)).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Verificar correo" }).length).toBeGreaterThan(0);
    expect(peticiones(SUSCRIPCION)).toHaveLength(0);
  });

  it("si el servidor responde correo_no_verificado, ofrece verificarlo", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [DESACTIVACION]: LIBRE,
      [PERFIL]: { status: 200, body: PERFIL_LAURA },
      [SUSCRIPCION]: {
        status: 403,
        body: {
          error: {
            codigo: "correo_no_verificado",
            mensaje: "Verifica tu correo para suscribirte a noticias.",
          },
        },
      },
    });
    renderRutas(rutas, "/perfil");
    await userEvent.click(await screen.findByRole("switch"));

    expect(await screen.findByRole("link", { name: "Verificar correo" })).toBeVisible();
    expect(screen.getByRole("switch")).not.toBeChecked();
  });

  it("el administrador no ve las suscripciones", async () => {
    servidor({ ...PERFIL_LAURA, rol: "admin", nombre_usuario: "cruiz" }, ADMIN);
    renderRutas(rutas, "/perfil");

    await campo("Nombres");
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });
});
