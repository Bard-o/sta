import { cop, fecha, hora } from "./format";

describe("cop (IU-06)", () => {
  it("usa punto de miles y sin decimales", () => {
    expect(cop(1250000)).toBe("$ 1.250.000");
    expect(cop(0)).toBe("$ 0");
    expect(cop(999.6)).toBe("$ 1.000");
  });

  it("antepone el signo de los movimientos", () => {
    expect(cop(500000, { sign: true })).toBe("+ $ 500.000");
    expect(cop(-800000, { sign: true })).toBe("− $ 800.000");
  });
});

describe("fecha y hora (IU-05)", () => {
  it("formatea dd/mm/aaaa y 24 h en la zona de la ciudad", () => {
    const salida = "2026-12-10T20:00:00Z";
    expect(fecha(salida, "America/Bogota")).toBe("10/12/2026");
    expect(hora(salida, "America/Bogota")).toBe("15:00");
    expect(hora("2026-12-10T23:30:00Z", "Europe/Madrid")).toBe("00:30");
    expect(fecha("2026-12-10T23:30:00Z", "Europe/Madrid")).toBe("11/12/2026");
  });
});
