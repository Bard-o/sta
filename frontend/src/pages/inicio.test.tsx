import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppLayout } from "@/layouts/app-layout";
import { InicioPage } from "@/pages/inicio";
import { NoticiasPage } from "@/pages/noticias";
import { ADMIN, responderApi, SIN_SESION, sesionDe } from "@/test/api";
import { noticia, noticiaPromocion, pagina } from "@/test/noticias";
import { renderRutas } from "@/test/render";

const rutas = [
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <InicioPage /> },
      { path: "/noticias", element: <NoticiasPage /> },
      { path: "/vuelos/:vueloId", element: <p>Detalle del vuelo</p> },
    ],
  },
];

const carrusel = (items: ReturnType<typeof noticia>[]) => ({ status: 200, body: items });

describe("Inicio público (HU-19)", () => {
  // HU-19: un visitante sin sesión puede ver el listado de noticias y el carrusel.
  it("un visitante sin sesión ve el carrusel y las noticias", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": carrusel([noticiaPromocion(1)]),
      "GET /api/v1/noticias": pagina([noticia(2), noticia(3)]),
    });
    renderRutas(rutas, "/");

    const carr = await screen.findByRole("region", { name: "Ofertas y vuelos nuevos" });
    expect(within(carr).getByText("Promoción vigente")).toBeVisible();
    expect(within(carr).getByRole("heading", { name: "Bogotá → Miami" })).toBeVisible();
    expect(within(carr).getByText("$ 1.386.000")).toBeVisible();
    expect(within(carr).getByText("$ 1.980.000")).toBeVisible();
    expect(await screen.findByText("Nuevo vuelo Pereira → Cartagena 2")).toBeVisible();
    expect(screen.getByRole("link", { name: "Ver todas las noticias" })).toHaveAttribute(
      "href",
      "/noticias",
    );
  });

  // HU-19: al hacer clic en un elemento del carrusel se abre el detalle del vuelo.
  it("«Ver vuelo» del carrusel abre el detalle del vuelo", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": carrusel([noticiaPromocion(1, "vigente", { vuelo_id: 76 })]),
      "GET /api/v1/noticias": pagina([]),
    });
    const { router } = renderRutas(rutas, "/");

    await userEvent.click(await screen.findByRole("link", { name: "Ver vuelo" }));

    expect(await screen.findByText("Detalle del vuelo")).toBeVisible();
    expect(router.state.location.pathname).toBe("/vuelos/76");
  });

  // HU-19: al hacer clic en una noticia se abre el detalle del vuelo.
  it("el título de una noticia abre el detalle del vuelo", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": carrusel([]),
      "GET /api/v1/noticias": pagina([noticia(2, { vuelo_id: 44 })]),
    });
    const { router } = renderRutas(rutas, "/");

    await userEvent.click(await screen.findByRole("link", { name: /Nuevo vuelo Pereira/ }));

    expect(router.state.location.pathname).toBe("/vuelos/44");
  });

  // HU-19: con más de 10 elementos posibles, el carrusel muestra solo 10, respetando el orden.
  it("el carrusel muestra como máximo 10 elementos, en el orden recibido", async () => {
    const doce = Array.from({ length: 12 }, (_, i) =>
      noticia(i + 1, {
        titulo: `Vuelo ${i + 1}`,
        destino: { ...noticia(1).destino, nombre: `Ciudad ${i + 1}` },
      }),
    );
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": carrusel(doce),
      "GET /api/v1/noticias": pagina([]),
    });
    renderRutas(rutas, "/");
    const user = userEvent.setup();

    const carr = await screen.findByRole("region", { name: "Ofertas y vuelos nuevos" });
    expect(within(carr).getByText("1 de 10")).toBeVisible();
    expect(within(carr).getByRole("heading", { name: "Pereira → Ciudad 1" })).toBeVisible();

    await user.click(within(carr).getByRole("button", { name: "Elemento siguiente" }));
    expect(within(carr).getByText("2 de 10")).toBeVisible();
    expect(within(carr).getByRole("heading", { name: "Pereira → Ciudad 2" })).toBeVisible();

    // Al llegar al último (el 10) y avanzar, vuelve al primero: nunca aparece el 11.
    for (let i = 0; i < 8; i++) {
      await user.click(within(carr).getByRole("button", { name: "Elemento siguiente" }));
    }
    expect(within(carr).getByText("10 de 10")).toBeVisible();
    await user.click(within(carr).getByRole("button", { name: "Elemento siguiente" }));
    expect(within(carr).getByText("1 de 10")).toBeVisible();
    await user.click(within(carr).getByRole("button", { name: "Elemento anterior" }));
    expect(within(carr).getByText("10 de 10")).toBeVisible();
  });

  // HU-19: la promoción vencida o agotada no aparece como vigente ni en el carrusel.
  it.each(["vencida", "agotada", "cancelada", "programada"] as const)(
    "una promoción %s no aparece en el carrusel aunque el servidor la envíe",
    async (estado) => {
      responderApi({
        "GET /api/v1/auth/me": SIN_SESION,
        "GET /api/v1/noticias/carrusel": carrusel([
          noticiaPromocion(1, estado, { vigente: true }),
          noticia(2),
        ]),
        "GET /api/v1/noticias": pagina([]),
      });
      renderRutas(rutas, "/");

      const carr = await screen.findByRole("region", { name: "Ofertas y vuelos nuevos" });
      expect(within(carr).queryByText("Promoción vigente")).not.toBeInTheDocument();
      expect(within(carr).getByText("Vuelo nuevo")).toBeVisible();
      expect(within(carr).getByText("1 de 1")).toBeVisible();
    },
  );

  it("sin elementos vigentes no muestra el carrusel", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": carrusel([noticiaPromocion(1, "vencida")]),
      "GET /api/v1/noticias": pagina([]),
    });
    renderRutas(rutas, "/");

    expect(await screen.findByText("Todavía no hay noticias.")).toBeVisible();
    expect(
      screen.queryByRole("region", { name: "Ofertas y vuelos nuevos" }),
    ).not.toBeInTheDocument();
  });

  // HU-19: las noticias de promociones vencidas o agotadas no se destacan como vigentes.
  it("en el listado, la promoción vigente se destaca y las demás dicen su estado", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": carrusel([]),
      "GET /api/v1/noticias": pagina([
        noticiaPromocion(1, "vigente", { titulo: "Promoción A" }),
        noticiaPromocion(2, "vencida", { titulo: "Promoción B" }),
        noticiaPromocion(3, "agotada", { titulo: "Promoción C" }),
        noticia(4, { titulo: "Vuelo D", vigente: false }),
        noticia(5, { titulo: "Vuelo E" }),
      ]),
    });
    renderRutas(rutas, "/");

    const item = async (titulo: string) =>
      (await screen.findByRole("link", { name: titulo })).closest("li")!;
    expect(within(await item("Promoción A")).getByText("Vigente")).toBeVisible();
    expect(within(await item("Promoción B")).getByText("Vencida")).toBeVisible();
    expect(within(await item("Promoción B")).queryByText("Vigente")).not.toBeInTheDocument();
    expect(within(await item("Promoción C")).getByText("Agotada")).toBeVisible();
    expect(within(await item("Vuelo D")).getByText("Vuelo no disponible")).toBeVisible();
    expect(
      within(await item("Vuelo E")).queryByText(/Vigente|Vencida|Agotada/),
    ).not.toBeInTheDocument();
  });

  // HU-19 / RF-55: no existe ninguna interfaz para crear noticias a mano.
  it("ni siquiera un administrador ve cómo crear una noticia", async () => {
    responderApi({
      "GET /api/v1/auth/me": sesionDe(ADMIN),
      "GET /api/v1/noticias/carrusel": carrusel([noticia(1)]),
      "GET /api/v1/noticias": pagina([noticia(2)]),
    });
    renderRutas(rutas, "/");
    await screen.findByText("Nuevo vuelo Pereira → Cartagena 2");

    expect(
      screen.queryByRole("button", { name: /(crear|publicar|nueva|agregar).*noticia/i }),
    ).toBeNull();
    expect(
      screen.queryByRole("link", { name: /(crear|publicar|nueva|agregar).*noticia/i }),
    ).toBeNull();
    expect(document.querySelector("form")).toBeNull();
  });

  it("si falla la carga muestra un aviso y deja reintentar", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": { status: 500, body: {} },
      "GET /api/v1/noticias": { status: 500, body: {} },
    });
    renderRutas(rutas, "/");

    expect(await screen.findByText(/No pudimos cargar las ofertas destacadas/)).toBeVisible();
    expect(await screen.findByText(/No pudimos cargar las noticias/)).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Reintentar" })).toHaveLength(2);
  });

  it("sin noticias lo dice", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias/carrusel": carrusel([]),
      "GET /api/v1/noticias": pagina([]),
    });
    renderRutas(rutas, "/");

    expect(await screen.findByText("Todavía no hay noticias.")).toBeVisible();
  });
});

describe("Todas las noticias (HU-19)", () => {
  it("pagina con ?pagina= y pide la página elegida al servidor", async () => {
    const pedidas: string[] = [];
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias": (url) => {
        pedidas.push(`${url.searchParams.get("pagina")}/${url.searchParams.get("por_pagina")}`);
        const pag = Number(url.searchParams.get("pagina"));
        return pagina([noticia(pag, { titulo: `Noticia de la página ${pag}` })], pag, 25, 10);
      },
    });
    const { router } = renderRutas(rutas, "/noticias");
    const user = userEvent.setup();

    expect(await screen.findByText("Noticia de la página 1")).toBeVisible();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await screen.findByText("Noticia de la página 2")).toBeVisible();
    expect(router.state.location.search).toBe("?pagina=2");
    expect(screen.getByRole("button", { name: "Página 2" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    await user.click(screen.getByRole("button", { name: "Página 3" }));
    expect(await screen.findByText("Noticia de la página 3")).toBeVisible();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
    expect(pedidas).toEqual(["1/10", "2/10", "3/10"]);
  });

  it("una página inválida en la URL se trata como la primera", async () => {
    const pedidas: string[] = [];
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias": (url) => {
        pedidas.push(String(url.searchParams.get("pagina")));
        return pagina([noticia(1)]);
      },
    });
    renderRutas(rutas, "/noticias?pagina=abc");

    await screen.findByText("Nuevo vuelo Pereira → Cartagena 1");
    expect(pedidas).toEqual(["1"]);
  });

  it("con una sola página no muestra la paginación", async () => {
    responderApi({
      "GET /api/v1/auth/me": SIN_SESION,
      "GET /api/v1/noticias": pagina([noticia(1)], 1, 1),
    });
    renderRutas(rutas, "/noticias");

    await screen.findByText("Nuevo vuelo Pereira → Cartagena 1");
    expect(screen.queryByRole("navigation", { name: "Paginación" })).not.toBeInTheDocument();
  });
});
