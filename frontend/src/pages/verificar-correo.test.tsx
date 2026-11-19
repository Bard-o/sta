import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schemas } from "@/api/client";
import { recordarRegreso, tomarRegreso } from "@/auth/verificacion";
import { VerificarCorreoPage } from "@/pages/verificar-correo";
import { CLIENTE, ROOT, responderApi, SIN_SESION, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  { path: "/verificar-correo", element: <VerificarCorreoPage /> },
  { path: "/login", element: <p>Pantalla de inicio de sesión</p> },
  { path: "/perfil", element: <p>Perfil</p> },
  { path: "/cliente", element: <p>Inicio del cliente</p> },
  { path: "/root", element: <p>Inicio del root</p> },
  { path: "/compra/viajeros", element: <p>Datos de los viajeros</p> },
  { path: "/mis-viajes", element: <p>Mis viajes</p> },
];

const SIN_VERIFICAR = { ...CLIENTE, email_verificado: false };

const perfil = (cambios: Partial<Schemas["PerfilSalida"]> = {}): Schemas["PerfilSalida"] => ({
  id: 12,
  nombre_usuario: "lauragomez",
  rol: "cliente",
  tipo_documento: "CC",
  numero_documento: "1088345921",
  nombres: "Laura",
  apellidos: "Gómez Ríos",
  fecha_nacimiento: "1995-03-14",
  lugar_nacimiento: {
    pais: "CO",
    pais_nombre: "Colombia",
    departamento: "66",
    departamento_nombre: "Risaralda",
    municipio: "66001",
    municipio_nombre: "Pereira",
    ciudad: null,
  },
  lugar_nacimiento_texto: "Pereira, Risaralda, Colombia",
  direccion_facturacion: "Cra. 7 # 19-28, Pereira",
  genero: "femenino",
  email: "laura.gomez@correo.co",
  email_verificado: false,
  email_pendiente: null,
  telefono: null,
  imagen_url: null,
  suscrito_noticias: false,
  ...cambios,
});

const VERIFICAR = "POST /api/v1/usuarios/verificacion";
const REENVIAR = "POST /api/v1/usuarios/me/verificacion/reenviar";
const PERFIL = "GET /api/v1/usuarios/me/perfil";
const SESION = "GET /api/v1/auth/me";
const ENLACE_INVALIDO = {
  status: 400,
  body: {
    error: {
      codigo: "enlace_invalido",
      mensaje: "Este enlace venció o ya fue usado. Pide uno nuevo.",
    },
  },
};

function peticiones(llave: string) {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === llave);
}

describe("S02 · Verificar correo con el enlace (HU-02)", () => {
  it("un enlace vigente verifica el correo, una sola vez, y habilita las funciones", async () => {
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [VERIFICAR]: { status: 204 } });
    renderRutas(rutas, "/verificar-correo?token=abc123");

    expect(await screen.findByRole("heading", { name: "Correo verificado" })).toBeVisible();
    expect(screen.getByText(/Ya puedes reservar, comprar y suscribirte a noticias/)).toBeVisible();
    expect(peticiones(VERIFICAR)).toHaveLength(1);
    expect(await peticiones(VERIFICAR)[0].json()).toEqual({ token: "abc123" });
  });

  it("vuelve a pedir la sesión para que el cliente quede como verificado", async () => {
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [VERIFICAR]: { status: 204 } });
    renderRutas(rutas, "/verificar-correo?token=abc123");
    await screen.findByRole("heading", { name: "Correo verificado" });

    await waitFor(() => expect(peticiones(SESION).length).toBeGreaterThanOrEqual(2));
  });

  it("funciona sin sesión (el enlace se abre en otro dispositivo) y ofrece iniciar sesión", async () => {
    responderApi({ [SESION]: SIN_SESION, [VERIFICAR]: { status: 204 } });
    renderRutas(rutas, "/verificar-correo?token=abc123");

    await screen.findByRole("heading", { name: "Correo verificado" });
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  });

  it("un enlace vencido o usado muestra el error y la opción de reenviar", async () => {
    responderApi({
      [SESION]: sesionDe(SIN_VERIFICAR),
      [VERIFICAR]: ENLACE_INVALIDO,
      [REENVIAR]: { status: 204 },
    });
    renderRutas(rutas, "/verificar-correo?token=vencido");

    expect(await screen.findByText(/Este enlace venció o ya fue usado/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Enviar un enlace nuevo" }));

    expect(
      await screen.findByText(/Te enviamos un enlace nuevo a laura\.gomez@correo\.co/),
    ).toBeVisible();
    expect(screen.getByText(/el anterior ya no funciona/)).toBeVisible();
    expect(peticiones(REENVIAR)).toHaveLength(1);
    expect(
      screen.queryByRole("button", { name: "Enviar un enlace nuevo" }),
    ).not.toBeInTheDocument();
  });

  it("un enlace vencido sin sesión pide iniciar sesión y vuelve a la verificación", async () => {
    responderApi({ [SESION]: SIN_SESION, [VERIFICAR]: ENLACE_INVALIDO });
    renderRutas(rutas, "/verificar-correo?token=vencido");

    await screen.findByText(/Este enlace venció o ya fue usado/);
    expect(
      screen.queryByRole("button", { name: "Enviar un enlace nuevo" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute(
      "href",
      "/login?next=%2Fverificar-correo",
    );
  });

  it("un fallo del servidor no se presenta como enlace vencido", async () => {
    responderApi({
      [SESION]: sesionDe(SIN_VERIFICAR),
      [VERIFICAR]: {
        status: 500,
        body: { error: { codigo: "error_interno", mensaje: "Algo salió mal. Intenta de nuevo." } },
      },
    });
    renderRutas(rutas, "/verificar-correo?token=abc123");

    expect(await screen.findByText("Algo salió mal. Intenta de nuevo.")).toBeVisible();
    expect(screen.queryByText(/venció o ya fue usado/)).not.toBeInTheDocument();
  });
});

describe("S02 · Estado de la cuenta y reenvío (HU-02)", () => {
  it("muestra a qué correo se envió el enlace y reenvía uno nuevo", async () => {
    responderApi({
      [SESION]: sesionDe(SIN_VERIFICAR),
      [PERFIL]: { status: 200, body: perfil() },
      [REENVIAR]: { status: 204 },
    });
    renderRutas(rutas, "/verificar-correo");

    expect(await screen.findByText("laura.gomez@correo.co")).toBeVisible();
    expect(screen.getByText(/Vence en 24 horas y solo funciona una vez/)).toBeVisible();
    expect(screen.getByText("Al reenviarlo, el enlace anterior deja de funcionar.")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Reenviar enlace" }));
    expect(
      await screen.findByText(/Te enviamos un enlace nuevo a laura\.gomez@correo\.co/),
    ).toBeVisible();
    expect(peticiones(REENVIAR)).toHaveLength(1);
  });

  it("con un cambio de correo pendiente, el enlace va al correo nuevo", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [PERFIL]: {
        status: 200,
        body: perfil({ email_verificado: true, email_pendiente: "laura.nueva@correo.co" }),
      },
    });
    renderRutas(rutas, "/verificar-correo");

    expect(await screen.findByText("laura.nueva@correo.co")).toBeVisible();
    expect(screen.queryByText("laura.gomez@correo.co")).not.toBeInTheDocument();
  });

  it("ofrece cambiar el correo desde el perfil", async () => {
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [PERFIL]: { status: 200, body: perfil() } });
    renderRutas(rutas, "/verificar-correo");

    await userEvent.click(await screen.findByRole("link", { name: "Cambiar correo" }));
    expect(await screen.findByText("Perfil")).toBeVisible();
  });

  it("si el servidor dice que ya está verificado, lo informa", async () => {
    responderApi({
      [SESION]: sesionDe(SIN_VERIFICAR),
      [PERFIL]: { status: 200, body: perfil() },
      [REENVIAR]: {
        status: 409,
        body: {
          error: { codigo: "correo_ya_verificado", mensaje: "Tu correo ya está verificado." },
        },
      },
    });
    renderRutas(rutas, "/verificar-correo");

    await userEvent.click(await screen.findByRole("button", { name: "Reenviar enlace" }));
    expect(await screen.findByText("Tu correo ya está verificado.")).toBeVisible();
  });

  it("un correo ya verificado no ofrece reenviar", async () => {
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [PERFIL]: { status: 200, body: perfil({ email_verificado: true }) },
    });
    renderRutas(rutas, "/verificar-correo");

    expect(await screen.findByText("Tu correo ya está verificado")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Reenviar enlace" })).not.toBeInTheDocument();
  });

  it("sin sesión lleva a iniciar sesión", async () => {
    responderApi({ [SESION]: SIN_SESION });
    const { router } = renderRutas(rutas, "/verificar-correo");

    await screen.findByText("Pantalla de inicio de sesión");
    expect(router.state.location.search).toBe("?next=%2Fverificar-correo");
  });

  it("el root no tiene correo: lo lleva a su inicio", async () => {
    responderApi({ [SESION]: sesionDe(ROOT) });
    renderRutas(rutas, "/verificar-correo");

    expect(await screen.findByText("Inicio del root")).toBeVisible();
  });
});

const DESTINO = "/compra/viajeros?seleccion=71";
const conVolver = (destino: string) => `/verificar-correo?volver=${encodeURIComponent(destino)}`;

// HU-02: lo que no es una ruta interna. El tabulador y el salto de línea los quita el navegador al
// resolver la URL y `\` lo lee como `/`, así que `/\t/malicioso.example` saldría de la aplicación.
const EXTERNOS = [
  "https://malicioso.example",
  "//malicioso.example",
  "/\\malicioso.example",
  "/\t/malicioso.example",
  "/\n/malicioso.example",
];

describe("S02 · Volver a la compra tras verificar (HU-02)", () => {
  it("HU-02: al llegar desde una compra muestra el aviso y el enlace para volver", async () => {
    // HU-02: «Verifica tu correo para comprar. Te llevamos a la verificación y luego vuelves».
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [PERFIL]: { status: 200, body: perfil() } });
    renderRutas(rutas, conVolver(DESTINO));

    expect(await screen.findByText(/Verifica tu correo para reservar o comprar\./)).toBeVisible();
    expect(screen.getByRole("link", { name: "Volver a tu compra" })).toHaveAttribute(
      "href",
      DESTINO,
    );
    expect(screen.getByRole("button", { name: "Reenviar enlace" })).toBeVisible();
  });

  it("HU-02: pulsar «Volver a tu compra» lleva al destino con la selección intacta", async () => {
    // HU-02: el cliente regresa a /compra/viajeros?seleccion=<id>, donde está su selección.
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [PERFIL]: { status: 200, body: perfil() } });
    const { router } = renderRutas(rutas, conVolver(DESTINO));

    await userEvent.click(await screen.findByRole("link", { name: "Volver a tu compra" }));

    expect(await screen.findByText("Datos de los viajeros")).toBeVisible();
    expect(router.state.location.pathname).toBe("/compra/viajeros");
    expect(router.state.location.search).toBe("?seleccion=71");
  });

  it("HU-02: con el correo ya verificado ofrece volver a la compra como acción principal", async () => {
    // HU-02: si verificó en otra pestaña, esta pantalla deja de pedir el enlace y ofrece volver.
    responderApi({
      [SESION]: sesionDe(CLIENTE),
      [PERFIL]: { status: 200, body: perfil({ email_verificado: true }) },
    });
    renderRutas(rutas, conVolver(DESTINO));

    expect(await screen.findByText("Tu correo ya está verificado")).toBeVisible();
    expect(screen.getByRole("link", { name: "Volver a tu compra" })).toHaveAttribute(
      "href",
      DESTINO,
    );
    expect(screen.queryByRole("link", { name: "Ir a mi inicio" })).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Verifica tu correo para reservar o comprar/),
    ).not.toBeInTheDocument();
  });

  it.each(EXTERNOS)(
    "HU-02: un destino externo (%j) se ignora y la pantalla se comporta como siempre",
    async (externo) => {
      // HU-02: solo se vuelve a rutas internas; un `volver` externo no ofrece ningún enlace.
      responderApi({
        [SESION]: sesionDe(SIN_VERIFICAR),
        [PERFIL]: { status: 200, body: perfil() },
      });
      renderRutas(rutas, conVolver(externo));

      expect(await screen.findByRole("button", { name: "Reenviar enlace" })).toBeVisible();
      expect(screen.queryByRole("link", { name: /Volver a/ })).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Verifica tu correo para reservar o comprar/),
      ).not.toBeInTheDocument();
    },
  );

  it.each(EXTERNOS)(
    "HU-02: verificado y con un destino externo (%j), ofrece ir al inicio",
    async (externo) => {
      // HU-02: un `volver` externo tampoco cambia la acción principal del correo ya verificado.
      responderApi({
        [SESION]: sesionDe(CLIENTE),
        [PERFIL]: { status: 200, body: perfil({ email_verificado: true }) },
      });
      renderRutas(rutas, conVolver(externo));

      expect(await screen.findByRole("link", { name: "Ir a mi inicio" })).toHaveAttribute(
        "href",
        "/cliente",
      );
      expect(screen.queryByRole("link", { name: /Volver a/ })).not.toBeInTheDocument();
    },
  );

  it("HU-02: si el destino es Mis viajes, el enlace lo nombra", async () => {
    // HU-02: pagar una reserva sin verificar vuelve a Mis viajes, no a «tu compra».
    const destino = "/mis-viajes?tipo=reserva&pagar=41";
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [PERFIL]: { status: 200, body: perfil() } });
    renderRutas(rutas, conVolver(destino));

    expect(await screen.findByRole("link", { name: "Volver a Mis viajes" })).toHaveAttribute(
      "href",
      destino,
    );
  });

  it("HU-02: la pestaña del enlace del correo ofrece volver a la compra una sola vez", async () => {
    // HU-02: el enlace llega sin `?volver=`; el destino sale de la copia que dejó la redirección.
    recordarRegreso(DESTINO);
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [VERIFICAR]: { status: 204 } });
    renderRutas(rutas, "/verificar-correo?token=abc123");

    expect(await screen.findByRole("heading", { name: "Correo verificado" })).toBeVisible();
    expect(await screen.findByRole("link", { name: "Volver a tu compra" })).toHaveAttribute(
      "href",
      DESTINO,
    );
    expect(tomarRegreso()).toBeNull();
  });

  it("HU-02: sin un destino guardado, la pestaña del enlace ofrece ir al inicio", async () => {
    // HU-02: sin copia (otro dispositivo o navegador) el comportamiento es el de siempre.
    responderApi({ [SESION]: sesionDe(SIN_VERIFICAR), [VERIFICAR]: { status: 204 } });
    renderRutas(rutas, "/verificar-correo?token=abc123");

    expect(await screen.findByRole("link", { name: "Ir a mi inicio" })).toHaveAttribute(
      "href",
      "/cliente",
    );
    expect(screen.queryByRole("link", { name: /Volver a/ })).not.toBeInTheDocument();
  });

  it("HU-02: un destino guardado externo o vencido no se ofrece", () => {
    // HU-02: la copia solo guarda rutas internas y deja de valer a las 24 horas, como el enlace.
    recordarRegreso("https://malicioso.example");
    expect(tomarRegreso()).toBeNull();

    // Solo la fecha: se guarda el 19/11/2026 y se lee 25 horas después.
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(new Date("2026-11-19T15:00:00Z"));
      recordarRegreso(DESTINO);
      vi.setSystemTime(new Date("2026-11-20T16:00:00Z"));
      expect(tomarRegreso()).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("HU-02: sin sesión, la pestaña del enlace lleva a iniciar sesión y de ahí a la compra", async () => {
    // HU-02: el destino guardado viaja como `next` del login, que lo valida como ruta interna.
    recordarRegreso(DESTINO);
    responderApi({ [SESION]: SIN_SESION, [VERIFICAR]: { status: 204 } });
    renderRutas(rutas, "/verificar-correo?token=abc123");

    await screen.findByRole("heading", { name: "Correo verificado" });
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute(
      "href",
      `/login?next=${encodeURIComponent(DESTINO)}`,
    );
  });

  it("HU-02: sin sesión, la verificación con `volver` pide iniciar sesión sin perder el destino", async () => {
    // HU-02: tras el login vuelve a /verificar-correo?volver=<destino> y de ahí a la compra.
    responderApi({ [SESION]: SIN_SESION });
    const { router } = renderRutas(rutas, conVolver(DESTINO));

    await screen.findByText("Pantalla de inicio de sesión");
    expect(router.state.location.pathname).toBe("/login");
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(conVolver(DESTINO));
  });
});
