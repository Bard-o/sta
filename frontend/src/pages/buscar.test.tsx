import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PaginaBusqueda, VueloBusqueda } from "@/pages/buscar/api";
import { BuscarPage } from "@/pages/buscar";
import { ADMIN, CLIENTE, responderApi, SIN_SESION, sesionDe } from "@/test/api";
import { renderRutas } from "@/test/render";
import { BOG, MDE, PEI } from "@/test/vuelos";

const SESION = "GET /api/v1/auth/me";
const BUSCAR = "GET /api/v1/busqueda/vuelos";
const CIUDADES = "GET /api/v1/ciudades";
const CARRITO = "GET /api/v1/carrito";
const AGREGAR = "POST /api/v1/carrito/selecciones";

const rutas = [
  { path: "/buscar", element: <BuscarPage /> },
  { path: "/login", element: <p>Inicio de sesión</p> },
  { path: "/carrito", element: <p>Tu carrito</p> },
];

const libre = { agotada: false, promocion: null };
const clase = (precio: number, disponibles: number, cambios = {}) => ({
  precio_base: precio,
  precio_vigente: precio,
  disponibles,
  ...libre,
  ...cambios,
});

/** STA-00031 Pereira → Bogotá, 15/04/2027 06:00 hora local (11:00Z), con promoción del 20 % en
 *  económica: $ 262.500 pasa a $ 210.000. */
const VUELO_31: VueloBusqueda = {
  id: 31,
  codigo: "STA-00031",
  tipo: "nacional",
  origen: { codigo: "PEI", nombre: "Pereira", zona_horaria: "America/Bogota" },
  destino: { codigo: "BOG", nombre: "Bogotá", zona_horaria: "America/Bogota" },
  salida: "2027-04-15T11:00:00Z",
  llegada: "2027-04-15T11:55:00Z",
  duracion_minutos: 55,
  economica: clase(262_500, 12, {
    precio_vigente: 210_000,
    promocion: { porcentaje: 20, fin: "2027-04-14T05:00:00Z" },
  }),
  primera: clase(690_000, 4),
  agotado: false,
};
const VUELO_42: VueloBusqueda = {
  ...VUELO_31,
  id: 42,
  codigo: "STA-00042",
  destino: { codigo: "MDE", nombre: "Medellín", zona_horaria: "America/Bogota" },
  salida: "2027-04-15T12:40:00Z",
  llegada: "2027-04-15T13:25:00Z",
  duracion_minutos: 45,
  economica: clase(185_000, 87),
  primera: clase(520_000, 19),
};
/** Sin sillas en económica pero con primera: sale marcado en esa clase (SUP-20). */
const VUELO_57: VueloBusqueda = {
  ...VUELO_42,
  id: 57,
  codigo: "STA-00057",
  economica: clase(320_000, 0, { agotada: true }),
  primera: clase(890_000, 3),
};
const VUELO_AGOTADO: VueloBusqueda = {
  ...VUELO_57,
  id: 58,
  codigo: "STA-00058",
  primera: clase(890_000, 0, { agotada: true }),
  agotado: true,
};

const pagina = (items: VueloBusqueda[], cambios: Partial<PaginaBusqueda> = {}): PaginaBusqueda => ({
  items,
  total: items.length,
  pagina: 1,
  por_pagina: 20,
  ...cambios,
});

const ok = (body: PaginaBusqueda) => ({ status: 200, body });
const error = (
  status: number,
  codigo: string,
  mensaje: string,
  campos?: Record<string, string>,
) => ({
  status,
  body: { error: { codigo, mensaje, campos } },
});

/** Las consultas de búsqueda que hizo la pantalla. */
const consultas = () =>
  vi
    .mocked(fetch)
    .mock.calls.map(([r]) => new URL((r as Request).url))
    .filter((u) => u.pathname === "/api/v1/busqueda/vuelos");
const ultima = () => consultas().at(-1)!.searchParams;

const base = (extra: Record<string, unknown> = {}) => ({
  [SESION]: SIN_SESION,
  [CIUDADES]: { status: 200, body: [PEI, BOG, MDE] },
  ...extra,
});

describe("S14 · Resultados de búsqueda (HU-20)", () => {
  it("lista cada vuelo con su ruta, horas locales, duración, precio vigente y disponibilidad por clase", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31, VUELO_42])) }));
    renderRutas(rutas, "/buscar");

    const pase = within(await screen.findByRole("article", { name: /STA-00031/ }));
    expect(pase.getByText("PEI")).toBeVisible();
    expect(pase.getByText("BOG")).toBeVisible();
    expect(pase.getByText("06:00")).toBeVisible();
    expect(pase.getByText("06:55")).toBeVisible();
    expect(pase.getByText("55 min, directo")).toBeVisible();
    expect(pase.getByText("Salida 15/04/2027")).toBeVisible();
    // Promoción: precio vigente, precio anterior tachado y la etiqueta con palabras.
    expect(pase.getByText("$ 210.000", { selector: ".sta-pass__price" })).toBeVisible();
    expect(pase.getByText("$ 262.500", { selector: ".sta-pass__old" })).toBeVisible();
    expect(pase.getByText("Promoción 20 % en económica")).toBeVisible();
    expect(pase.getByText(/Económica \$ 210\.000: quedan 12/)).toBeVisible();
    expect(pase.getByText(/Primera clase \$ 690\.000: quedan 4/)).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "2 vuelos" })).toBeVisible();
  });

  it("lleva a la búsqueda de ida y regreso (HU-21)", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31])) }));
    renderRutas(rutas, "/buscar");

    expect(await screen.findByRole("link", { name: "Ida y regreso" })).toHaveAttribute(
      "href",
      "/buscar/ida-y-regreso",
    );
  });

  it("pide primero por precio, de 20 en 20", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31])) }));
    renderRutas(rutas, "/buscar");
    await screen.findByRole("article", { name: /STA-00031/ });

    expect(ultima().get("orden")).toBe("precio");
    expect(ultima().get("por_pagina")).toBe("20");
    expect(ultima().get("pagina")).toBe("1");
    expect(screen.getByRole("heading", { level: 1, name: "1 vuelo" })).toBeVisible();
  });

  it("combina los filtros: origen, destino, tipo, fechas, franja, duración, precio y clase", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31])) }));
    renderRutas(rutas, "/buscar");
    await screen.findByRole("article", { name: /STA-00031/ });
    const filtros = within(screen.getByRole("search", { name: "Filtros de búsqueda" }));

    await userEvent.type(filtros.getByLabelText("Código del vuelo"), "STA-0003");
    await userEvent.selectOptions(filtros.getByLabelText("Origen"), "PEI");
    await userEvent.selectOptions(filtros.getByLabelText("Destino"), "BOG");
    await userEvent.selectOptions(filtros.getByLabelText("Tipo"), "nacional");
    await userEvent.type(filtros.getByLabelText("Salida desde"), "2027-04-15");
    await userEvent.type(filtros.getByLabelText("Salida hasta"), "2027-04-18");
    await userEvent.selectOptions(filtros.getByLabelText("Franja horaria"), "manana");
    await userEvent.type(filtros.getByLabelText("Duración mín. (min)"), "30");
    await userEvent.type(filtros.getByLabelText("Duración máx. (min)"), "120");
    await userEvent.type(filtros.getByLabelText("Precio mín. ($)"), "200000");
    await userEvent.type(filtros.getByLabelText("Precio máx. ($)"), "400000");
    await userEvent.selectOptions(filtros.getByLabelText("Clase"), "economica");
    await userEvent.click(filtros.getByRole("button", { name: "Aplicar filtros" }));

    await waitFor(() => expect(ultima().get("origen")).toBe("PEI"));
    const q = ultima();
    expect(Object.fromEntries(q)).toMatchObject({
      codigo: "STA-0003",
      origen: "PEI",
      destino: "BOG",
      tipo: "nacional",
      fecha_desde: "2027-04-15",
      fecha_hasta: "2027-04-18",
      hora_desde: "06:00",
      hora_hasta: "11:59",
      duracion_min: "30",
      duracion_max: "120",
      precio_min: "200000",
      precio_max: "400000",
      clase: "economica",
      pagina: "1",
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "1 vuelo desde Pereira" }),
    ).toBeVisible();
    expect(
      screen.getByText(/a Bogotá, 15\/04\/2027 al 18\/04\/2027, económica, mañana, nacionales/),
    ).toBeVisible();
  });

  it("los filtros viven en la dirección: recargar con ellos los aplica", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31])) }));
    renderRutas(rutas, "/buscar?origen=PEI&precio_min=200000&precio_max=400000&clase=economica");

    await screen.findByRole("article", { name: /STA-00031/ });

    expect(ultima().get("origen")).toBe("PEI");
    expect(ultima().get("precio_min")).toBe("200000");
    expect(screen.getByLabelText("Precio máx. ($)")).toHaveValue(400000);
    expect(screen.getByLabelText("Origen")).toHaveValue("PEI");
  });

  it("un rango inválido se marca junto al campo y no se envía (precio, fecha y duración)", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31])) }));
    renderRutas(rutas, "/buscar");
    await screen.findByRole("article", { name: /STA-00031/ });
    const enviadas = consultas().length;
    const filtros = within(screen.getByRole("search", { name: "Filtros de búsqueda" }));

    await userEvent.type(filtros.getByLabelText("Precio mín. ($)"), "200000");
    await userEvent.type(filtros.getByLabelText("Precio máx. ($)"), "100000");
    await userEvent.type(filtros.getByLabelText("Salida desde"), "2027-04-18");
    await userEvent.type(filtros.getByLabelText("Salida hasta"), "2027-04-15");
    await userEvent.type(filtros.getByLabelText("Duración mín. (min)"), "90");
    await userEvent.type(filtros.getByLabelText("Duración máx. (min)"), "30");
    await userEvent.click(filtros.getByRole("button", { name: "Aplicar filtros" }));

    expect(filtros.getByText("Debe ser mayor o igual que el precio mínimo.")).toBeVisible();
    expect(filtros.getByText("La fecha final no puede ser anterior a la inicial.")).toBeVisible();
    expect(filtros.getByText("Debe ser mayor o igual que la duración mínima.")).toBeVisible();
    expect(filtros.getByLabelText("Precio máx. ($)")).toHaveAttribute("aria-invalid", "true");
    expect(consultas()).toHaveLength(enviadas);
  });

  it("el rango_invalido del servidor se muestra junto al campo que corresponde", async () => {
    responderApi(
      base({
        [BUSCAR]: error(422, "rango_invalido", "Revisa los rangos marcados.", {
          precio_max: "Debe ser mayor o igual que el precio mínimo.",
          hora_hasta: "La hora final no puede ser anterior a la inicial.",
        }),
      }),
    );
    renderRutas(rutas, "/buscar?precio_min=200000&precio_max=300000&franja=tarde");

    const filtros = within(await screen.findByRole("search", { name: "Filtros de búsqueda" }));
    expect(await filtros.findByText("Debe ser mayor o igual que el precio mínimo.")).toBeVisible();
    expect(filtros.getByText("La hora final no puede ser anterior a la inicial.")).toBeVisible();
  });

  it("un vuelo sin cupo sale como agotado y no se puede agregar", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_AGOTADO])) }));
    renderRutas(rutas, "/buscar");

    const pase = within(await screen.findByRole("article", { name: /STA-00058/ }));
    expect(pase.getByText("Agotado", { selector: ".sta-badge" })).toBeVisible();
    expect(pase.getByRole("button", { name: "Agotado" })).toBeDisabled();
  });

  it("con una clase elegida, el vuelo agotado en esa clase sale marcado y no desaparece (SUP-20)", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_57])) }));
    renderRutas(rutas, "/buscar?clase=economica");

    const pase = within(await screen.findByRole("article", { name: /STA-00057/ }));
    expect(pase.getByText("Agotado en económica")).toBeVisible();
    expect(pase.getByRole("button", { name: "Agotado" })).toBeDisabled();
    expect(pase.getByText("$ 320.000", { selector: ".sta-pass__price" })).toBeVisible();
  });

  it("cambiar el orden vuelve a consultar y pone la primera página", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31, VUELO_42])) }));
    renderRutas(rutas, "/buscar");
    await screen.findByRole("article", { name: /STA-00031/ });

    await userEvent.selectOptions(screen.getByLabelText("Ordenar por"), "duracion");

    await waitFor(() => expect(ultima().get("orden")).toBe("duracion"));
    expect(ultima().get("pagina")).toBe("1");
  });

  it("pagina de 20 en 20", async () => {
    responderApi(
      base({
        [BUSCAR]: (url: URL) =>
          ok(pagina([VUELO_31], { total: 45, pagina: Number(url.searchParams.get("pagina")) })),
      }),
    );
    renderRutas(rutas, "/buscar");
    await screen.findByRole("article", { name: /STA-00031/ });

    await userEvent.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => expect(ultima().get("pagina")).toBe("2"));
    expect(screen.getByRole("button", { name: "Anterior" })).toBeEnabled();
  });

  it("sin resultados invita a cambiar los filtros y deja quitarlos", async () => {
    responderApi(
      base({
        [BUSCAR]: (url: URL) => ok(pagina(url.searchParams.get("origen") ? [] : [VUELO_31])),
      }),
    );
    renderRutas(rutas, "/buscar?origen=MDE");

    expect(await screen.findByText("No encontramos vuelos")).toBeVisible();
    expect(screen.getByText(/Ningún vuelo cumple todos los filtros/)).toBeVisible();

    // Hay dos «Quitar filtros»: el del panel y el del estado vacío; cualquiera restablece la búsqueda.
    const vacio = within(screen.getByText("No encontramos vuelos").closest("section")!);
    await userEvent.click(vacio.getByRole("button", { name: "Quitar filtros" }));

    expect(await screen.findByRole("article", { name: /STA-00031/ })).toBeVisible();
    expect(ultima().get("origen")).toBeNull();
  });
});

const conSesion = (usuario: Parameters<typeof sesionDe>[0], extra: Record<string, unknown> = {}) =>
  base({
    [SESION]: sesionDe(usuario),
    "GET /api/v1/usuarios/me/perfil": { status: 200, body: {} },
    [CARRITO]: { status: 200, body: { selecciones: [], cantidad: 0, total: 0 } },
    [BUSCAR]: ok(pagina([VUELO_31, VUELO_42])),
    ...extra,
  });

const cuerpoAgregar = () => {
  const peticion = vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .find((r) => r.method === "POST" && new URL(r.url).pathname === "/api/v1/carrito/selecciones");
  return peticion?.clone().json() as Promise<unknown> | undefined;
};

describe("S14 · Agregar al carrito desde los resultados (HU-22)", () => {
  it("el cliente elige la clase y los viajeros y agrega el vuelo", async () => {
    responderApi(conSesion(CLIENTE, { [AGREGAR]: { status: 201, body: {} } }));
    renderRutas(rutas, "/buscar");

    const pase = within(await screen.findByRole("article", { name: /STA-00031/ }));
    await userEvent.click(pase.getByRole("button", { name: "Agregar STA-00031 al carrito" }));
    const dialogo = within(
      await screen.findByRole("dialog", { name: "Agregar STA-00031 al carrito" }),
    );
    await userEvent.selectOptions(dialogo.getByLabelText("Clase"), "primera");
    await userEvent.selectOptions(dialogo.getByLabelText("Viajeros"), "3");
    expect(dialogo.getByText(/Total estimado:/)).toHaveTextContent("$ 2.070.000");
    await userEvent.click(dialogo.getByRole("button", { name: "Agregar al carrito" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await cuerpoAgregar()).toEqual({
      tramos: [{ vuelo_id: 31, clase: "primera" }],
      viajeros: 3,
    });
  });

  it("clase_agotada y limite_tiquetes se muestran en el resultado que falló", async () => {
    responderApi(
      conSesion(CLIENTE, {
        [AGREGAR]: error(
          409,
          "limite_tiquetes",
          "Un cliente puede tener máximo 5 tiquetes activos en el mismo vuelo.",
        ),
      }),
    );
    renderRutas(rutas, "/buscar");

    const pase = await screen.findByRole("article", { name: /STA-00031/ });
    const resultado = pase.parentElement!;
    await userEvent.click(
      within(pase).getByRole("button", { name: "Agregar STA-00031 al carrito" }),
    );
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Agregar al carrito" }),
    );

    expect(await within(resultado).findByText(/máximo 5 tiquetes activos/)).toBeVisible();
    // El otro resultado no se toca.
    const otro = (await screen.findByRole("article", { name: /STA-00042/ })).parentElement!;
    expect(within(otro).queryByText(/máximo 5 tiquetes activos/)).toBeNull();
  });

  it("clase_agotada al agregar se muestra en el resultado", async () => {
    responderApi(
      conSesion(CLIENTE, {
        [AGREGAR]: error(409, "clase_agotada", "No quedan sillas suficientes en esta clase."),
      }),
    );
    renderRutas(rutas, "/buscar");

    const pase = await screen.findByRole("article", { name: /STA-00042/ });
    await userEvent.click(
      within(pase).getByRole("button", { name: "Agregar STA-00042 al carrito" }),
    );
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Agregar al carrito" }),
    );

    expect(
      await within(pase.parentElement!).findByText("No quedan sillas suficientes en esta clase."),
    ).toBeVisible();
  });

  it("en el diálogo no se puede agregar una clase agotada", async () => {
    responderApi(conSesion(CLIENTE, { [BUSCAR]: ok(pagina([VUELO_57])) }));
    renderRutas(rutas, "/buscar");

    const pase = await screen.findByRole("article", { name: /STA-00057/ });
    await userEvent.click(
      within(pase).getByRole("button", { name: "Agregar STA-00057 al carrito" }),
    );
    const dialogo = within(await screen.findByRole("dialog"));
    // Económica está agotada: el diálogo abre en primera clase, que sí tiene sillas.
    expect(dialogo.getByLabelText("Clase")).toHaveValue("primera");
    await userEvent.selectOptions(dialogo.getByLabelText("Clase"), "economica");

    expect(dialogo.getByText("Esta clase no tiene sillas disponibles.")).toBeVisible();
    expect(dialogo.getByRole("button", { name: "Agregar al carrito" })).toBeDisabled();
  });

  it("un vuelo que ya está en el carrito lo dice con palabras", async () => {
    const enCarrito = {
      selecciones: [{ id: 1, tramos: [{ vuelo: { id: 31 } }] }],
      cantidad: 1,
      total: 0,
    };
    responderApi(conSesion(CLIENTE, { [CARRITO]: { status: 200, body: enCarrito } }));
    renderRutas(rutas, "/buscar");

    const pase = within(await screen.findByRole("article", { name: /STA-00031/ }));
    expect(await pase.findByText("En tu carrito")).toBeVisible();
    expect(
      within(screen.getByRole("article", { name: /STA-00042/ })).queryByText("En tu carrito"),
    ).toBeNull();
  });

  it("al visitante agregar lo lleva a iniciar sesión y vuelve a la misma búsqueda", async () => {
    responderApi(base({ [BUSCAR]: ok(pagina([VUELO_31])) }));
    renderRutas(rutas, "/buscar?origen=PEI");

    const enlace = await screen.findByRole("link", { name: /Agregar STA-00031 al carrito/ });

    expect(enlace).toHaveAttribute("href", "/login?next=%2Fbuscar%3Forigen%3DPEI");
  });

  it("el administrador consulta pero no ve el botón Agregar", async () => {
    responderApi(conSesion(ADMIN));
    renderRutas(rutas, "/buscar");

    await screen.findByRole("article", { name: /STA-00031/ });

    expect(screen.queryByRole("button", { name: /Agregar/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /Agregar/ })).toBeNull();
  });
});
