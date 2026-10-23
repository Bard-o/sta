import { aIsoColombia, instanteColombia, precioConDescuento } from "./promocion";

describe("precioConDescuento (RF-24)", () => {
  it("aplica el porcentaje sobre el precio base", () => {
    expect(precioConDescuento(2450000, 40)).toBe(1470000);
    expect(precioConDescuento(280000, 10)).toBe(252000);
  });

  it("redondea hacia abajo a pesos enteros", () => {
    expect(precioConDescuento(100001, 33)).toBe(67000);
    expect(precioConDescuento(999, 90)).toBe(99);
  });
});

describe("hora de Colombia", () => {
  it("agrega el desfase UTC-5", () => {
    expect(aIsoColombia("2026-10-15T10:00")).toBe("2026-10-15T10:00:00-05:00");
  });

  it("el instante equivale a 5 horas más en UTC", () => {
    expect(instanteColombia("2026-10-15T10:00")).toBe(Date.parse("2026-10-15T15:00:00Z"));
  });

  it("devuelve NaN con un valor incompleto", () => {
    expect(instanteColombia("")).toBeNaN();
  });
});
