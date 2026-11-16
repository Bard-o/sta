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
    email: "carlos.ruiz@avianco.test",
    nombres: "Carlos",
    apellidos: "Ruiz",
    estado: "activo",
    invitacion_expira_en: null,
    creado_en: "2026-09-02T15:20:00Z",
  },
  {
    id: 5,
    nombre_usuario: "jtorres",
    email: "jorge.torres@avianco.test",
    nombres: null,
    apellidos: null,
    estado: "invitacion_pendiente",
    invitacion_expira_en: "2099-12-31T23:59:00Z",
    creado_en: "2026-09-29T21:40:00Z",
  },
  {
    id: 6,
    nombre_usuario: "pgomez",
    email: "paula.gomez@avianco.test",
    nombres: null,
    apellidos: null,
    estado: "invitacion_vencida",
    invitacion_expira_en: "2026-10-01T14:00:00Z",
    creado_en: "2026-09-27T14:00:00Z",
  },
  {
    id: 2,
    nombre_usuario: "amejia",
    email: "andres.mejia@avianco.test",
    nombres: "Andrés",
    apellidos: "Mejía",
    estado: "inactivo",
    invitacion_expira_en: null,
    creado_en: "2026-08-12T14:00:00Z",
  },
];

const NUEVO: Schemas["AdministradorSalida"] = {
  id: 1001,
  nombre_usuario: "nuevo.admin",
  email: "nuevo.admin@avianco.test",
  nombres: null,
  apellidos: null,
  estado: "invitacion_pendiente",
  invitacion_expira_en: "2099-12-31T23:59:00Z",
  creado_en: "2026-10-22T15:00:00Z",
};

const SESION = "GET /api/v1/auth/me";
const LISTA = "GET /api/v1/administradores";
const CREAR = "POST /api/v1/administradores";
const desactivar = (id: number) => `POST /api/v1/administradores/${id}/desactivar`;
const reactivar = (id: number) => `POST /api/v1/administradores/${id}/reactivar`;
const reenviar = (id: number) => `POST /api/v1/administradores/${id}/invitacion`;

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

describe("S06 · Invitar administradores (HU-10)", () => {
  it("envía usuario y correo, sin contraseña, y muestra la invitación pendiente", async () => {
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
    await user.type(screen.getByLabelText("Correo"), "nuevo.admin@avianco.test");
    await user.click(screen.getByRole("button", { name: "Enviar invitación" }));

    expect(await screen.findByText(/Invitamos a nuevo\.admin/)).toBeVisible();
    expect(await cuerpoEnviado(CREAR)).toEqual({
      nombre_usuario: "nuevo.admin",
      email: "nuevo.admin@avianco.test",
    });
    expect(await screen.findByRole("row", { name: /nuevo\.admin/ })).toBeVisible();
    expect(fila("nuevo.admin").getByText(/Invitación pendiente/)).toBeVisible();
    expect(fila("nuevo.admin").getByText("Sin completar")).toBeVisible();
    expect(screen.getByLabelText("Nombre de usuario")).toHaveValue("");
    expect(screen.getByLabelText("Correo")).toHaveValue("");
  });

  it("no envía un correo con formato inválido", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [LISTA]: lista() });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Nombre de usuario"), "nuevo.admin");
    await user.type(screen.getByLabelText("Correo"), "sin-arroba");
    await user.click(screen.getByRole("button", { name: "Enviar invitación" }));

    expect(await screen.findByText("Escribe un correo válido.")).toBeVisible();
    expect(peticiones(CREAR)).toHaveLength(0);
  });

  it("rechaza el nombre o el correo que ya existen junto a su campo", async () => {
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista(),
      [CREAR]: {
        status: 409,
        body: {
          error: {
            codigo: "datos_duplicados",
            mensaje: "Ya existe una cuenta con estos datos.",
            campos: {
              nombre_usuario: "Ese nombre de usuario ya existe.",
              email: "Ya existe un administrador con este correo.",
            },
          },
        },
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Nombre de usuario"), "cruiz");
    await user.type(screen.getByLabelText("Correo"), "carlos.ruiz@avianco.test");
    await user.click(screen.getByRole("button", { name: "Enviar invitación" }));

    expect(await screen.findByText("Ese nombre de usuario ya existe.")).toBeVisible();
    expect(screen.getByText("Ya existe un administrador con este correo.")).toBeVisible();
  });

  it("el formulario solo envía los dos campos del contrato, sin rol ni contraseña", async () => {
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista(),
      [CREAR]: { status: 201, body: NUEVO },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    expect(await screen.findByLabelText("Nombre de usuario")).toBeVisible();
    expect(screen.getByLabelText("Correo")).toBeVisible();
    expect(screen.queryByLabelText(/contraseña/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/rol/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /root/ })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Nombre de usuario"), "nuevo.admin");
    await user.type(screen.getByLabelText("Correo"), "nuevo.admin@avianco.test");
    await user.click(screen.getByRole("button", { name: "Enviar invitación" }));

    expect(Object.keys(await cuerpoEnviado(CREAR)).sort()).toEqual(["email", "nombre_usuario"]);
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

describe("S06 · Listado, reenvío y estados (HU-10, HU-11)", () => {
  it("muestra los cuatro estados y los nombres faltantes", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [LISTA]: lista() });
    renderRutas(rutas, "/root/administradores");

    await screen.findByRole("row", { name: /cruiz/ });
    expect(fila("cruiz").getByText("Activo")).toBeVisible();
    expect(fila("amejia").getByText("Inactivo")).toBeVisible();
    expect(fila("jtorres").getByText(/Invitación pendiente/)).toBeVisible();
    expect(fila("jtorres").getByText("Sin completar")).toBeVisible();
    expect(fila("pgomez").getByText("Invitación vencida")).toBeVisible();
    expect(fila("jtorres").getByText("jorge.torres@avianco.test")).toBeVisible();
  });

  it("reenvía la invitación pendiente y avisa que el enlace anterior dejó de servir", async () => {
    let reenviado = false;
    const actualizado = {
      ...ADMINISTRADORES[1],
      invitacion_expira_en: "2099-12-31T23:59:00Z",
    };
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista(),
      [reenviar(5)]: () => {
        reenviado = true;
        return { status: 200, body: actualizado };
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reenviar invitación a jtorres" }));

    expect(await screen.findByText(/Reenviamos la invitación a jorge\.torres/)).toBeVisible();
    expect(reenviado).toBe(true);
    expect(peticiones(reenviar(5))).toHaveLength(1);
  });

  it("pide el correo para reenviar una cuenta antigua que no lo tiene", async () => {
    const sinCorreo = { ...ADMINISTRADORES[2], email: null };
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: lista([ADMINISTRADORES[0], sinCorreo]),
      [reenviar(6)]: {
        status: 200,
        body: { ...sinCorreo, email: "paula.gomez@avianco.test" },
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reenviar invitación a pgomez" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText(/no tiene un correo guardado/)).toBeVisible();
    await user.type(within(dialogo).getByLabelText("Correo"), "paula.gomez@avianco.test");
    await user.click(within(dialogo).getByRole("button", { name: "Enviar invitación" }));

    expect(await screen.findByText(/Reenviamos la invitación a paula\.gomez/)).toBeVisible();
    expect(await cuerpoEnviado(reenviar(6))).toEqual({ email: "paula.gomez@avianco.test" });
  });

  it("una fila inactiva ofrece reactivar y no desactivar", async () => {
    responderApi({ [SESION]: sesionDe(ROOT), [LISTA]: lista() });
    renderRutas(rutas, "/root/administradores");

    await screen.findByRole("row", { name: /amejia/ });
    expect(fila("amejia").getByRole("button", { name: "Reactivar a amejia" })).toBeVisible();
    expect(fila("amejia").queryByRole("button", { name: /Desactivar/ })).not.toBeInTheDocument();
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

  it("reactivar un registro incompleto lo deja con la invitación vencida", async () => {
    let reactivado = false;
    const inactivo = { ...ADMINISTRADORES[1], estado: "inactivo" as const };
    const devuelto = { ...ADMINISTRADORES[1], estado: "invitacion_vencida" as const };
    responderApi({
      [SESION]: sesionDe(ROOT),
      [LISTA]: () =>
        lista(
          reactivado
            ? [ADMINISTRADORES[0], devuelto, ADMINISTRADORES[2], ADMINISTRADORES[3]]
            : [ADMINISTRADORES[0], inactivo, ADMINISTRADORES[2], ADMINISTRADORES[3]],
        ),
      [reactivar(5)]: () => {
        reactivado = true;
        return { status: 200, body: devuelto };
      },
    });
    renderRutas(rutas, "/root/administradores");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Reactivar a jtorres" }));

    expect(await screen.findByText(/Reenvíale la invitación para que pueda entrar/)).toBeVisible();
    await waitFor(() => expect(fila("jtorres").getByText("Invitación vencida")).toBeVisible());
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
