import { render, screen } from "@testing-library/react";
import { Pasos } from "./pasos";

describe("Pasos", () => {
  it("marca el paso actual y dice con palabras cuáles están hechos", () => {
    render(<Pasos pasos={["Vuelos", "Viajeros", "Pago"]} actual={1} />);

    expect(screen.getByRole("list", { name: "Pasos de la compra" })).toBeVisible();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Viajeros");
    expect(screen.getByText("(hecho)")).toBeInTheDocument();
    expect(screen.getByText("(paso actual)")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("en el último paso todos los anteriores están hechos", () => {
    render(<Pasos pasos={["Vuelos", "Viajeros", "Pago"]} actual={2} />);

    expect(screen.getAllByText("(hecho)")).toHaveLength(2);
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Pago");
  });
});
