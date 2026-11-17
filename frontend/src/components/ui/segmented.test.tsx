import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Segmented } from "./segmented";

const OPCIONES = [
  { value: "todas", label: "Todas" },
  { value: "vigente", label: "Vigentes" },
] as const;

describe("Segmented", () => {
  it("marca la opción activa con aria-pressed y avisa el cambio", async () => {
    const onChange = vi.fn();
    render(<Segmented label="Estado" options={[...OPCIONES]} value="todas" onChange={onChange} />);

    expect(screen.getByRole("group", { name: "Estado" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Todas", pressed: true })).toBeVisible();
    expect(screen.getByRole("button", { name: "Vigentes", pressed: false })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Vigentes" }));
    expect(onChange).toHaveBeenCalledWith("vigente");
  });
});
