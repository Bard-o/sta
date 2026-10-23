import { cop, desfase, duracion, fecha, fechaHora, fechaRelativa, hora } from "./format";

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

describe("desfase (IU-05)", () => {
  it("da el desfase de la zona en ese instante, con horario de verano", () => {
    expect(desfase("2026-12-10T20:00:00Z", "America/Bogota")).toBe("UTC-5");
    expect(desfase("2026-12-10T20:00:00Z", "Europe/Madrid")).toBe("UTC+1");
    expect(desfase("2026-07-10T20:00:00Z", "Europe/Madrid")).toBe("UTC+2");
    expect(desfase("2026-07-10T20:00:00Z", "America/New_York")).toBe("UTC-4");
    expect(desfase("2026-12-10T20:00:00Z", "Europe/London")).toBe("UTC");
    expect(desfase("2026-12-10T20:00:00Z", "Asia/Kolkata")).toBe("UTC+5:30");
  });
});

describe("fechaHora", () => {
  it("junta fecha y hora de la ciudad", () => {
    expect(fechaHora("2026-12-10T20:00:00Z", "America/Bogota")).toBe("10/12/2026 15:00");
  });
});

describe("fechaRelativa (S13)", () => {
  const ahora = new Date("2026-10-20T17:00:00Z"); // 12:00 en Colombia
  it("dice hoy y ayer según la hora de Colombia", () => {
    expect(fechaRelativa("2026-10-20T14:12:00Z", ahora)).toBe("Hoy, 09:12");
    expect(fechaRelativa("2026-10-19T21:40:00Z", ahora)).toBe("Ayer, 16:40");
  });
  it("usa dd/mm/aaaa para días anteriores", () => {
    expect(fechaRelativa("2026-09-27T17:30:00Z", ahora)).toBe("27/09/2026");
  });
  it("una hora de madrugada UTC aún es el día anterior en Colombia", () => {
    expect(fechaRelativa("2026-10-20T03:00:00Z", ahora)).toBe("Ayer, 22:00");
  });
});

describe("duracion", () => {
  it.each([
    [600, "10 h"],
    [50, "50 min"],
    [90, "1 h 30 min"],
    [1439, "23 h 59 min"],
  ])("%i minutos → %s", (minutos, esperado) => {
    expect(duracion(minutos)).toBe(esperado);
  });
});
