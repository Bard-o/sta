import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schemas } from "@/api/client";
import { RequireRole } from "@/auth/require-role";
import { AppLayout } from "@/layouts/app-layout";
import { AdministradoresPage } from "@/pages/administradores";
import { ADMIN, CLIENTE, ROOT, responderApi, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  {
    element: <AppLayout />,
    children: [
      {
        element: <RequireRole roles={["root"]} />,
        children: [{ path: "/root/administradores", element: <AdministradoresPage /> }],
      },
      { path: "/root", element: <p>Inicio del root</p> },
      { path: "/admin", element: <p>Inicio del administrador</p> },
      { path: "/cliente", element: <p>Inicio del cliente</p> },
      { path: "/login", element: <p>Pantalla de inicio de sesión</p> },
    ],
  },
];

const ADMINISTRADORES: Schemas["AdministradorSalida"][] = [
  {
    id: 3,
    nombre_usuario: "cruiz",
    nombres: "Carlos",
    apellidos: "Ruiz",
    estado: "activo",
    creado_en: "2026-09-02T15:20:00Z",
  },
  {
    id: 5,
    nombre_usuario: "jtorres",
    nombres: null,
    apellidos: null,
    estado: "registro_incompleto",
    creado_en: "2026-09-29T21:40:00Z",
  },
  {
    id: 2,
    nombre_usuario: "amejia",
    nombres: "Andrés",
    apellidos: "Mejía",
    estado: "inactivo",
    creado_en: "2026-08-12T14:00:00Z",
  },
];

const NUEVO: Schemas["AdministradorSalida"] = {
  id: 1001,
  nombre_usuario: "nuevo.admin",
  nombres: null,
  apellidos: null,
  estado: "registro_incompleto",
  creado_en: "2026-10-22T15:00:00Z",
};

const SESION = "GET /api/v1/auth/me";
const LISTA = "GET /api/v1/administradores";
const CREAR = "POST /api/v1/administradores";
const desactivar = (id: number) => `POST /api/v1/administradores/${id}/desactivar`;
const reactivar = (id: number) => `POST /api/v1/administradores/${id}/reactivar`;

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

async function cuerpoEnviado(llave: string) {
  await waitFor(() => expect(peticiones(llave)).toHaveLength(1));
  return (await peticiones(llave)[0].json()) as Record<string, unknown>;
}

function fila(usuario: string) {
  return within(screen.getByRole("row", { name: new RegExp(usuario) }));
}

const lista = (items: Schemas["AdministradorSalida"][] = ADMINISTRADORES) => ({
  status: 200,
  body: items,
});

describe("S06 · Crear administrador (HU-10)", () => {
  it("crea un administrador y lo muestra como registro incompleto", async () => {
    let creado = false;
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: () => lista(creado ? [NUEVO, ...ADMINISTRADORES] : ADMINISTRADORES),
      [CREAR]: () => {
        creado = true;
        return { status: 201, body: NUEVO };
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Nombre de usuario"), "nuevo.admin");
    await user.type(screen.getByLabelText("Contraseña temporal"), "Temporal123");
    await user.click(screen.getByRole("button", { name: "Crear administrador" }));

    expect(await screen.findByText(/Creamos la cuenta de nuevo\.admin/)).toBeVisible();
    expect(await cuerpoEnviado(CREAR)).toEqual({
      nombre_usuario: "nuevo.admin",
      contrasena_temporal: "Temporal123",
    });
    expect(await screen.findByRole("row", { name: /nuevo\.admin/ })).toBeVisible();
    expect(fila("nuevo.admin").getByText("Registro incompleto")).toBeVisible();
    expect(fila("nuevo.admin").getByText("Sin completar")).toBeVisible();
    expect(screen.getByLabelText("Nombre de usuario")).toHaveValue("");
  });

  it("no envía una contraseña que no cumple la política", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [LISTA]: lista() });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Nombre de usuario"), "nuevo.admin");
    await user.type(screen.getByLabelText("Contraseña temporal"), "corta");
    await user.click(screen.getByRole("button", { name: "Crear administrador" }));

    expect(
      await screen.findByText("La contraseña debe tener al menos 8 caracteres."),
    ).toBeVisible();
    expect(peticiones(CREAR)).toHaveLength(0);
  });

  it("rechaza un nombre de usuario que ya existe junto al campo", async () => {
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista(),
      [CREAR]: {
        status: 409,
        body: {
          error: {
            codigo: "datos_duplicados",
            mensaje: "Ya existe una cuenta con estos datos.",
            campos: { nombre_usuario: "Ese nombre de usuario ya existe." },
          },
        },
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Nombre de usuario"), "cruiz");
    await user.type(screen.getByLabelText("Contraseña temporal"), "Temporal123");
    await user.click(screen.getByRole("button", { name: "Crear administrador" }));

    expect(await screen.findByText("Ese nombre de usuario ya existe.")).toBeVisible();
    expect(screen.queryByRole("row", { name: /nuevo\.admin/ })).not.toBeInTheDocument();
  });

  it("el formulario solo crea administradores y no envía un rol", async () => {
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista(),
      [CREAR]: { status: 201, body: NUEVO },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    expect(await screen.findByLabelText("Nombre de usuario")).toBeVisible();
    expect(screen.getByLabelText("Contraseña temporal")).toBeVisible();
    expect(screen.queryByLabelText(/rol/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /root/ })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Nombre de usuario"), "nuevo.admin");
    await user.type(screen.getByLabelText("Contraseña temporal"), "Temporal123");
    await user.click(screen.getByRole("button", { name: "Crear administrador" }));

    expect(Object.keys(await cuerpoEnviado(CREAR)).sort()).toEqual([
      "contrasena_temporal",
      "nombre_usuario",
    ]);
  });

  it.each([
    ["administrador", ADMIN, "Inicio del administrador"],
    ["cliente", CLIENTE, "Inicio del cliente"],
  ] as const)("un %s no ve la ruta ni el enlace", async (_rol, usuario, destino) => {
    responderApi({ [SESION]: sesionDe(usuario) });
    renderRutas(rutas, "/root/administradores");

    expect(await screen.findByText(destino)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Administradores" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Administradores" })).not.toBeInTheDocument();
  });
});

describe("S06 · Desactivar o reactivar administrador (HU-11)", () => {
  it("una fila inactiva se muestra como inactiva y ofrece reactivar", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [LISTA]: lista() });
    renderRutas(rutas, "/root/administradores");

    await screen.findByRole("row", { name: /amejia/ });
    expect(fila("amejia").getByText("Inactivo")).toBeVisible();
    expect(fila("amejia").getByRole("button", { name: "Reactivar a amejia" })).toBeVisible();
    expect(fila("amejia").queryByRole("button", { name: /Desactivar/ })).not.toBeInTheDocument();
  });

  it("la lista muestra los tres estados y los nombres faltantes", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [LISTA]: lista() });
    renderRutas(rutas, "/root/administradores");

    await screen.findByRole("row", { name: /cruiz/ });
    expect(fila("cruiz").getByText("Activo")).toBeVisible();
    expect(fila("amejia").getByText("Inactivo")).toBeVisible();
    expect(fila("jtorres").getByText("Registro incompleto")).toBeVisible();
    expect(fila("jtorres").getByText("Sin completar")).toBeVisible();
  });

  it("pide confirmación antes de desactivar y no la envía si se vuelve", async () => {
    let desactivado = false;
    const inactivo = { ...ADMINISTRADORES[0], estado: "inactivo" as const };
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: () => lista(desactivado ? [inactivo, ...ADMINISTRADORES.slice(1)] : ADMINISTRADORES),
      [desactivar(3)]: () => {
        desactivado = true;
        return { status: 200, body: inactivo };
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Desactivar a cruiz" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText(/¿Desactivar al administrador cruiz\?/)).toBeVisible();
    expect(within(dialogo).getByText(/No podrá iniciar sesión/)).toBeVisible();

    await user.click(within(dialogo).getByRole("button", { name: "Volver" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(peticiones(desactivar(3))).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Desactivar a cruiz" }));
    await user.click(await screen.findByRole("button", { name: "Desactivar administrador" }));

    expect(await screen.findByText(/Desactivamos a cruiz/)).toBeVisible();
    expect(peticiones(desactivar(3))).toHaveLength(1);
    await waitFor(() => expect(fila("cruiz").getByText("Inactivo")).toBeVisible());
  });

  it("reactivar llama al endpoint correcto y actualiza la fila", async () => {
    let reactivado = false;
    const activo = { ...ADMINISTRADORES[2], estado: "activo" as const };
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: () =>
        lista(reactivado ? [ADMINISTRADORES[0], ADMINISTRADORES[1], activo] : ADMINISTRADORES),
      [reactivar(2)]: () => {
        reactivado = true;
        return { status: 200, body: activo };
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reactivar a amejia" }));

    expect(await screen.findByText(/Reactivamos a amejia/)).toBeVisible();
    expect(peticiones(reactivar(2))).toHaveLength(1);
    await waitFor(() => expect(fila("amejia").getByText("Activo")).toBeVisible());
  });

  it("reactivar un registro incompleto lo deja otra vez incompleto", async () => {
    let reactivado = false;
    const incompleto = { ...ADMINISTRADORES[1], estado: "inactivo" as const };
    const devuelto = { ...ADMINISTRADORES[1] };
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: () =>
        lista(
          reactivado
            ? [ADMINISTRADORES[0], devuelto, ADMINISTRADORES[2]]
            : [ADMINISTRADORES[0], incompleto, ADMINISTRADORES[2]],
        ),
      [reactivar(5)]: () => {
        reactivado = true;
        return { status: 200, body: devuelto };
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reactivar a jtorres" }));

    expect(await screen.findByText(/Reactivamos a jtorres/)).toBeVisible();
    await waitFor(() => expect(fila("jtorres").getByText("Registro incompleto")).toBeVisible());
  });
});

describe("S06 · Estados de error del contrato", () => {
  it("si el estado cambió en otro lado, avisa", async () => {
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista(),
      [reactivar(2)]: {
        status: 409,
        body: {
          error: { codigo: "estado_invalido", mensaje: "El administrador ya está activo." },
        },
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reactivar a amejia" }));

    expect(await screen.findByText("El administrador ya está activo.")).toBeVisible();
  });

  it("si el administrador ya no existe, avisa", async () => {
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista(),
      [desactivar(5)]: {
        status: 404,
        body: { error: { codigo: "no_encontrado", mensaje: "El administrador no existe." } },
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Desactivar a jtorres" }));
    await user.click(await screen.findByRole("button", { name: "Desactivar administrador" }));

    expect(await screen.findByText("El administrador no existe.")).toBeVisible();
  });

  it("si falla la lista, ofrece reintentar", async () => {
    let intentos = 0;
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: () => {
        intentos += 1;
        return intentos === 1
          ? {
              status: 500,
              body: {
                error: { codigo: "error_interno", mensaje: "Algo salió mal. Intenta de nuevo." },
              },
            }
          : lista();
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    expect(await screen.findByText(/No pudimos cargar los administradores/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("row", { name: /cruiz/ })).toBeVisible();
  });

  it("sin administradores, lo dice", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [LISTA]: lista([]) });
    renderRutas(rutas, "/root/administradores");

    expect(await screen.findByText("Todavía no hay administradores.")).toBeVisible();
  });
});
