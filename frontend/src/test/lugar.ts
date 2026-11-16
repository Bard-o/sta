import { screen } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";

type User = ReturnType<typeof userEvent.setup>;

type Lugar = {
  pais?: string;
  departamento?: string;
  municipio?: string;
  ciudad?: string;
};

/** Elige un lugar de nacimiento en el Combobox como lo haría una persona: abre, busca y elige. */
export async function elegirLugar(
  user: User,
  { pais = "Colombia", departamento, municipio, ciudad }: Lugar = {},
) {
  await user.click(await screen.findByRole("combobox", { name: "País" }));
  await user.click(await screen.findByRole("option", { name: pais }));

  if (departamento) {
    await user.click(await screen.findByRole("combobox", { name: "Departamento" }));
    await user.click(await screen.findByRole("option", { name: departamento }));
  }
  if (municipio) {
    await user.click(await screen.findByRole("combobox", { name: "Municipio" }));
    await user.click(await screen.findByRole("option", { name: municipio }));
  }
  if (ciudad) {
    await user.type(await screen.findByLabelText("Ciudad"), ciudad);
  }
}
