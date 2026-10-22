import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SoloVisitantes } from "@/auth/require-role";
import { RegistroPage } from "@/pages/registro";
import { CLIENTE, responderApi, SIN_SESION } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  {
    element: <SoloVisitantes />,
    children: [
      { path: "/registro", element: <RegistroPage /> },
      { path: "/login", element: <p>Pantalla de inicio de sesión</p> },
    ],
  },
  { path: "/cliente", element: <p>Inicio del cliente</p> },
];

const REGISTRO = "POST /api/v1/usuarios/registro";
const IMAGEN = "PUT /api/v1/usuarios/me/imagen";

const ok = {
  "GET /api/v1/auth/me": SIN_SESION,
  [REGISTRO]: { status: 201, body: CLIENTE },
  [IMAGEN]: { status: 200, body: {} },
};

type Opciones = { sinPolitica?: boolean; sobrescribe?: Record<string, string> };

/** Llena el formulario con datos válidos (los de Laura Gómez del wireframe S01). */
async function llenar({ sinPolitica, sobrescribe = {} }: Opciones = {}) {
  const user = userEvent.setup();
  const datos: Record<string, string> = {
    "Número de documento": "1088345921",
    Nombres: "Laura",
    Apellidos: "Gómez Ríos",
    "Fecha de nacimiento": "1995-03-14",
    "Lugar de nacimiento": "Pereira, Risaralda",
    "Dirección de facturación": "Cra. 7 # 19-28, Pereira",
    "Correo electrónico": "laura.gomez@correo.co",
    "Nombre de usuario": "lauragomez",
    Contraseña: "Clave1234",
    ...sobrescribe,
  };
  await user.selectOptions(await screen.findByLabelText("Género"), "femenino");
  for (const [etiqueta, valor] of Object.entries(datos)) {
    const campo = screen.getByLabelText(etiqueta);
    await user.clear(campo);
    if (valor) await user.type(campo, valor);
  }
  if (!sinPolitica)
    await user.click(screen.getByRole("checkbox", { name: /política de tratamiento/ }));
  return user;
}

const crear = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: "Crear cuenta" }));

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

beforeEach(() => {
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: () => "blob:vista", revokeObjectURL: () => {} }),
  );
});

describe("S01 · Registro de cliente (HU-01)", () => {
  it("un registro con datos válidos crea la cuenta y lleva al inicio del cliente", async () => {
    responderApi(ok);
    const { router } = renderRutas(rutas, "/registro");
    const user = await llenar();
    await crear(user);

    await screen.findByText("Inicio del cliente");
    expect(router.state.location.pathname).toBe("/cliente");
    const [pedido] = peticiones(REGISTRO);
    expect(await pedido.json()).toEqual({
      tipo_documento: "CC",
      numero_documento: "1088345921",
      genero: "femenino",
      nombres: "Laura",
      apellidos: "Gómez Ríos",
      fecha_nacimiento: "1995-03-14",
      lugar_nacimiento: "Pereira, Risaralda",
      direccion_facturacion: "Cra. 7 # 19-28, Pereira",
      email: "laura.gomez@correo.co",
      nombre_usuario: "lauragomez",
      contrasena: "Clave1234",
      acepta_politica: true,
    });
    expect(peticiones(IMAGEN)).toHaveLength(0);
  });

  it("rechaza el registro sin aceptar la política de datos, junto a la casilla", async () => {
    responderApi(ok);
    renderRutas(rutas, "/registro");
    const user = await llenar({ sinPolitica: true });
    await crear(user);

    expect(await screen.findByText(/Debes aceptar la política de tratamiento/)).toBeInTheDocument();
    expect(peticiones(REGISTRO)).toHaveLength(0);
  });

  it("indica el campo con error: fecha futura, correo mal formado y contraseña débil", async () => {
    responderApi(ok);
    renderRutas(rutas, "/registro");
    const user = await llenar({
      sobrescribe: {
        "Fecha de nacimiento": "2999-03-14",
        "Correo electrónico": "laura.gomez",
        Contraseña: "abcdefgh",
      },
    });
    await crear(user);

    expect(
      await screen.findByText("La fecha de nacimiento no puede ser futura."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Escribe un correo válido/)).toBeInTheDocument();
    expect(screen.getByText("La contraseña debe tener al menos un número.")).toBeInTheDocument();
    expect(peticiones(REGISTRO)).toHaveLength(0);
  });

  it("rechaza una contraseña de menos de 8 caracteres", async () => {
    responderApi(ok);
    renderRutas(rutas, "/registro");
    const user = await llenar({ sobrescribe: { Contraseña: "Ab1" } });
    await crear(user);

    expect(
      await screen.findByText("La contraseña debe tener al menos 8 caracteres."),
    ).toBeInTheDocument();
  });

  it("muestra junto a cada campo los duplicados que reporta el servidor", async () => {
    responderApi({
      ...ok,
      [REGISTRO]: {
        status: 409,
        body: {
          error: {
            codigo: "datos_duplicados",
            mensaje: "Ya existe una cuenta con estos datos.",
            campos: {
              nombre_usuario: "Ese nombre de usuario ya está en uso.",
              email: "Ya existe una cuenta con este correo.",
            },
          },
        },
      },
    });
    renderRutas(rutas, "/registro");
    const user = await llenar();
    await crear(user);

    const usuario = await screen.findByLabelText("Nombre de usuario");
    await waitFor(() => expect(usuario).toBeInvalid());
    expect(screen.getByText("Ese nombre de usuario ya está en uso.")).toBeInTheDocument();
    expect(screen.getByText("Ya existe una cuenta con este correo.")).toBeInTheDocument();
    expect(screen.getByLabelText("Número de documento")).toBeValid();
    expect(screen.queryByText("Inicio del cliente")).not.toBeInTheDocument();
  });

  it("permite registrarse a un menor de edad (la restricción aplica al volar)", async () => {
    responderApi(ok);
    renderRutas(rutas, "/registro");
    const user = await llenar({
      sobrescribe: { "Fecha de nacimiento": "2018-06-01", "Número de documento": "RC123456" },
    });
    await user.selectOptions(screen.getByLabelText("Tipo de documento"), "RC");
    await crear(user);

    await screen.findByText("Inicio del cliente");
  });

  it("sube la imagen de perfil como multipart después de crear la cuenta", async () => {
    const adjuntar = vi.spyOn(FormData.prototype, "append");
    onTestFinished(() => adjuntar.mockRestore());
    responderApi(ok);
    renderRutas(rutas, "/registro");
    const user = await llenar();
    const archivo = new File(["x"], "laura.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Archivo de imagen de perfil"), archivo);
    expect(await screen.findByAltText("Tu imagen de perfil")).toBeInTheDocument();
    await crear(user);

    await screen.findByText("Inicio del cliente");
    const [subida] = peticiones(IMAGEN);
    expect(subida.headers.get("Content-Type")).toMatch(/^multipart\/form-data; boundary=/);
    // En jsdom el File no es el de Node: `Request.formData()` falla y el cuerpo serializado
    // pierde el contenido. Se comprueba que el formulario lleva el archivo elegido.
    expect(adjuntar).toHaveBeenCalledWith("imagen", archivo);
  });

  it("rechaza una imagen que no es JPG o PNG o pesa más de 2 MB, sin bloquear el registro", async () => {
    responderApi(ok);
    renderRutas(rutas, "/registro");
    const user = await llenar();
    const entrada = screen.getByLabelText("Archivo de imagen de perfil");

    await user.upload(entrada, new File(["x"], "foto.jpeg", { type: "image/jpeg" }));
    const grande = new File(["x"], "grande.png", { type: "image/png" });
    Object.defineProperty(grande, "size", { value: 3 * 1024 * 1024 });
    await user.upload(entrada, grande);
    expect(await screen.findByText(/pesa más de 2 MB/)).toBeInTheDocument();
    expect(screen.queryByAltText("Tu imagen de perfil")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Quitar" }));
    await crear(user);
    await screen.findByText("Inicio del cliente");
    expect(peticiones(IMAGEN)).toHaveLength(0);
  });

  it("si falla la subida de la imagen, la cuenta ya está creada y entra igual", async () => {
    responderApi({
      ...ok,
      [IMAGEN]: {
        status: 422,
        body: { error: { codigo: "datos_invalidos", mensaje: "Revisa los campos marcados." } },
      },
    });
    renderRutas(rutas, "/registro");
    const user = await llenar();
    await user.upload(
      screen.getByLabelText("Archivo de imagen de perfil"),
      new File(["x"], "laura.png", { type: "image/png" }),
    );
    await crear(user);

    await screen.findByText("Inicio del cliente");
  });

  it("enlaza con el inicio de sesión", async () => {
    responderApi(ok);
    renderRutas(rutas, "/registro");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: "Inicia sesión" }));
    expect(await screen.findByText("Pantalla de inicio de sesión")).toBeInTheDocument();
  });
});
