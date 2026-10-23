import { screen } from "@testing-library/react";
import { BajaNoticiasPage } from "@/pages/noticias-baja";
import { responderApi } from "@/test/api";
import { renderRutas } from "@/test/render";

const rutas = [{ path: "/noticias/baja", element: <BajaNoticiasPage /> }];
const BAJA = "POST /api/v1/usuarios/suscripcion/baja";

function peticiones() {
  return vi
    .mocked(fetch)
    .mock.calls.map(([r]) => r as Request)
    .filter((r) => `${r.method} ${new URL(r.url).pathname}` === BAJA);
}

describe("Baja de noticias desde el correo (HU-08)", () => {
  it("da de baja con el enlace, sin iniciar sesión y con una sola petición", async () => {
    responderApi({ [BAJA]: { status: 204 } });
    renderRutas(rutas, "/noticias/baja?token=abc123");

    expect(await screen.findByText(/te diste de baja/)).toBeVisible();
    expect(peticiones()).toHaveLength(1);
    expect(await peticiones()[0].json()).toEqual({ token: "abc123" });
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
  });

  it("un enlace inválido lo dice y manda al perfil para darse de baja desde allí", async () => {
    responderApi({
      [BAJA]: {
        status: 400,
        body: { error: { codigo: "enlace_invalido", mensaje: "Enlace inválido." } },
      },
    });
    renderRutas(rutas, "/noticias/baja?token=vencido");

    expect(await screen.findByText(/Este enlace de baja no es válido/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Ir a mi perfil" })).toHaveAttribute("href", "/perfil");
  });

  it("sin token no hace ninguna petición", async () => {
    responderApi({});
    renderRutas(rutas, "/noticias/baja");

    expect(await screen.findByText(/Este enlace de baja no es válido/)).toBeVisible();
    expect(peticiones()).toHaveLength(0);
  });

  it("un fallo del servidor no se presenta como enlace inválido", async () => {
    responderApi({
      [BAJA]: {
        status: 500,
        body: { error: { codigo: "error_interno", mensaje: "Algo salió mal. Intenta de nuevo." } },
      },
    });
    renderRutas(rutas, "/noticias/baja?token=abc123");

    expect(await screen.findByText("Algo salió mal. Intenta de nuevo.")).toBeVisible();
    expect(screen.queryByText(/no es válido/)).not.toBeInTheDocument();
  });
});
