import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SelectorTema } from "./selector-tema";

const html = document.documentElement;

afterEach(() => {
  html.removeAttribute("data-theme");
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("Selector de tema", () => {
  it("sin tema aplicado ofrece cambiar a Noche, porque el claro es el de por defecto", () => {
    render(<SelectorTema />);
    expect(screen.getByRole("button", { name: "Cambiar al tema noche" })).toBeVisible();
  });

  it("cambia a Noche, lo aplica en <html> y lo recuerda", async () => {
    render(<SelectorTema />);

    await userEvent.click(screen.getByRole("button", { name: "Cambiar al tema noche" }));

    expect(html).toHaveAttribute("data-theme", "noche");
    expect(localStorage.getItem("sta-tema")).toBe("noche");
    expect(screen.getByRole("button", { name: "Cambiar al tema claro" })).toBeVisible();
  });

  it("vuelve al claro desde Noche", async () => {
    html.setAttribute("data-theme", "noche");
    render(<SelectorTema />);

    await userEvent.click(screen.getByRole("button", { name: "Cambiar al tema claro" }));

    expect(html).toHaveAttribute("data-theme", "claro");
    expect(localStorage.getItem("sta-tema")).toBe("claro");
  });

  it("si el navegador no deja guardar, el cambio igual se aplica", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("lleno", "QuotaExceededError");
    });
    render(<SelectorTema />);

    await userEvent.click(screen.getByRole("button", { name: "Cambiar al tema noche" }));

    expect(html).toHaveAttribute("data-theme", "noche");
  });
});
