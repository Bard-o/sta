import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuevaTarjetaPage } from "@/pages/nueva-tarjeta";
import { responderApi } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [
  { path: "/monedero/tarjetas/nueva", element: <NuevaTarjetaPage /> },
  { path: "/monedero/recargar", element: <p>Recargar monedero</p> },
  { path: "/monedero", element: <p>Monedero</p> },
];

const CREAR = "POST /api/v1/monedero/tarjetas";
const NUMERO = "4242424242424242";
const CVV = "907";

const TARJETA = {
  id: 24,
  tipo: "credito",
  franquicia: "visa",
  titular: "LAURA GOMEZ RIOS",
  numero_enmascarado: "**** 4242",
  vencimiento: "08/28",
  vencida: false,
  creada_en: "2026-11-16T12:00:00Z",
};

const error = (codigo: string, mensaje: string, campos?: Record<string, string>) => ({
  status: 422,
  body: { error: { codigo, mensaje, ...(campos ? { campos } : {}) } },
});

const peticiones = (metodo: string, ruta: string) =>
  vi
    .mocked(fetch)
    .mock.calls.map(([entrada]) => entrada as Request)
    .filter((peticion) => peticion.method === metodo && new URL(peticion.url).pathname === ruta);

async function llenar({
  numero = NUMERO,
  vencimiento = "08/28",
  cvv = CVV,
  titular = "LAURA GOMEZ RIOS",
}: Partial<{ numero: string; vencimiento: string; cvv: string; titular: string }> = {}) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Número"), numero);
  await user.type(screen.getByLabelText("Nombre del titular"), titular);
  await user.type(screen.getByLabelText("Vence"), vencimiento);
  await user.type(screen.getByLabelText("CVV"), cvv);
  return user;
}

beforeEach(() => {
  // «Ahora» es el 16/11/2026 07:00 en Colombia.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-16T12:00:00Z"));
});
afterEach(() => vi.useRealTimers());

describe("Registrar tarjeta (HU-28)", () => {
  it("registra una tarjeta válida y vuelve a la recarga con sus parámetros", async () => {
    responderApi({ [CREAR]: { status: 201, body: TARJETA } });
    const volver = "/monedero/recargar?faltante=300000&codigo=K7Q2PX";
    const { router } = renderRutas(
      rutas,
      `/monedero/tarjetas/nueva?volver=${encodeURIComponent(volver)}`,
    );

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/monedero/recargar"));
    expect(router.state.location.search).toBe("?faltante=300000&codigo=K7Q2PX");

    const [peticion] = peticiones("POST", "/api/v1/monedero/tarjetas");
    expect(await peticion.json()).toEqual({
      tipo: "credito",
      titular: "LAURA GOMEZ RIOS",
      numero: NUMERO,
      vencimiento: "08/28",
      cvv: CVV,
    });
  });

  it("sin `volver` continúa en el monedero", async () => {
    responderApi({ [CREAR]: { status: 201, body: TARJETA } });
    const { router } = renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/monedero"));
  });

  // HU-28: un número que no pasa Luhn se marca en su campo y no llega a la API.
  it("marca el número cuando no pasa Luhn, sin llamar a la API", async () => {
    responderApi({});
    renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar({ numero: "4242 4242 4242 4241" });
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    expect(await screen.findByText("El número no es válido. Revisa los dígitos.")).toBeVisible();
    expect(screen.getByLabelText("Número")).toHaveAttribute("aria-invalid", "true");
    expect(fetch).not.toHaveBeenCalled();
  });

  // HU-28: una tarjeta vencida se marca en su campo y no llega a la API.
  it("marca el vencimiento anterior al mes actual", async () => {
    responderApi({});
    renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar({ vencimiento: "05/26" });
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    expect(await screen.findByText("La tarjeta está vencida.")).toBeVisible();
    expect(screen.getByLabelText("Vence")).toHaveAttribute("aria-invalid", "true");
    expect(fetch).not.toHaveBeenCalled();
  });

  // HU-28: el error del servidor también se muestra junto al campo.
  it("muestra junto al número el error tarjeta_invalida del servidor", async () => {
    responderApi({
      [CREAR]: error("tarjeta_invalida", "Revisa los datos de la tarjeta.", {
        numero: "El número no es válido. Revisa los dígitos.",
      }),
    });
    renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    expect(await screen.findByText("El número no es válido. Revisa los dígitos.")).toBeVisible();
    expect(screen.getByLabelText("Número")).toHaveAttribute("aria-invalid", "true");
    expect(peticiones("POST", "/api/v1/monedero/tarjetas")).toHaveLength(1);
  });

  // HU-28: una tarjeta vencida que el servidor rechaza se marca en su campo.
  it("muestra junto al vencimiento el error tarjeta_vencida del servidor", async () => {
    responderApi({
      [CREAR]: error("tarjeta_vencida", "La tarjeta está vencida.", {
        vencimiento: "La tarjeta está vencida.",
      }),
    });
    renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    expect(await screen.findByText("La tarjeta está vencida.")).toBeVisible();
    expect(screen.getByLabelText("Vence")).toHaveAttribute("aria-invalid", "true");
    expect(peticiones("POST", "/api/v1/monedero/tarjetas")).toHaveLength(1);
  });

  it("muestra los datos_invalidos del servidor en el campo que los causó", async () => {
    responderApi({
      [CREAR]: error("datos_invalidos", "Revisa los campos marcados.", {
        cvv: "El formato del CVV no es válido.",
      }),
    });
    renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    expect(await screen.findByText("El formato del CVV no es válido.")).toBeVisible();
    expect(screen.getByLabelText("CVV")).toHaveAttribute("aria-invalid", "true");
  });

  // RNF-12: el número completo y el CVV no quedan en la URL, el almacenamiento ni la caché.
  it("no deja el número ni el CVV en la URL, el almacenamiento ni la caché de TanStack", async () => {
    responderApi({ [CREAR]: { status: 201, body: TARJETA } });
    const { router, queryClient } = renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/monedero"));

    expect(router.state.location.search).not.toContain(NUMERO);
    expect(router.state.location.search).not.toContain(CVV);

    for (const almacen of [window.localStorage, window.sessionStorage]) {
      for (let indice = 0; indice < almacen.length; indice += 1) {
        const clave = almacen.key(indice);
        const guardado = clave ? (almacen.getItem(clave) ?? "") : "";
        expect(guardado).not.toContain(NUMERO);
        expect(guardado).not.toContain(CVV);
      }
    }

    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    const cache = JSON.stringify(
      queryClient
        .getQueryCache()
        .getAll()
        .map((consulta) => [consulta.queryKey, consulta.state.data]),
    );
    expect(cache).not.toContain(NUMERO);
    expect(cache).not.toContain(CVV);
  });

  it("ignora un `volver` que no es una ruta interna y vuelve al monedero", async () => {
    responderApi({ [CREAR]: { status: 201, body: TARJETA } });
    const { router } = renderRutas(
      rutas,
      `/monedero/tarjetas/nueva?volver=${encodeURIComponent("//evil.example/robar")}`,
    );

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/monedero"));
  });

  it("muestra un aviso cuando el servidor falla sin marcar un campo", async () => {
    responderApi({
      [CREAR]: {
        status: 500,
        body: { error: { codigo: "error_interno", mensaje: "Ocurrió un error inesperado." } },
      },
    });
    renderRutas(rutas, "/monedero/tarjetas/nueva");

    const user = await llenar();
    await user.click(screen.getByRole("button", { name: "Registrar tarjeta" }));

    expect(await screen.findByText("Ocurrió un error inesperado.")).toBeVisible();
  });
});
