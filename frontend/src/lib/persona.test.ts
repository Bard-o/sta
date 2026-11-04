import { camposPersona, fechaMinimaNacimiento, MENSAJE_EDAD_MAXIMA } from "@/lib/persona";

describe("fechaMinimaNacimiento (RF-03, SUP-43)", () => {
  it.each([
    ["2026-11-03", "1906-11-03"],
    ["2024-02-29", "1904-02-29"], // 1904 fue bisiesto: mismo mes y día.
    ["2020-02-29", "1900-03-01"], // 1900 no fue bisiesto: la mínima es el 1 de marzo.
    ["2100-02-28", "1980-02-28"],
    ["2000-02-29", "1880-02-29"], // 1880 fue bisiesto.
  ])("con hoy en %s la mínima es %s", (hoy, minima) => {
    expect(fechaMinimaNacimiento(hoy)).toBe(minima);
  });
});

describe("camposPersona.fecha_nacimiento (RF-03, SUP-43)", () => {
  beforeEach(() => {
    // Solo la fecha: «hoy» es 03/11/2026.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-03T15:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  const mensajes = (valor: string) =>
    camposPersona.fecha_nacimiento.safeParse(valor).error?.issues.map((i) => i.message) ?? [];

  it("acepta a quien cumple exactamente 120 años hoy y a un niño de 2 años", () => {
    expect(camposPersona.fecha_nacimiento.safeParse("1906-11-03").success).toBe(true);
    expect(camposPersona.fecha_nacimiento.safeParse("2024-11-03").success).toBe(true);
  });

  it("rechaza una fecha de hace más de 120 años con el mensaje de edad máxima", () => {
    expect(mensajes("1906-11-02")).toEqual([MENSAJE_EDAD_MAXIMA]);
  });

  it("rechaza una fecha futura con el mensaje de fecha futura", () => {
    expect(mensajes("2026-11-04")).toEqual(["La fecha de nacimiento no puede ser futura."]);
  });

  it("un campo vacío solo muestra el mensaje de requerido", () => {
    expect(mensajes("")).toEqual(["Escribe tu fecha de nacimiento."]);
  });
});
