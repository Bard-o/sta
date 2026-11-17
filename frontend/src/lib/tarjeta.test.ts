import {
  agruparNumero,
  NOMBRE_FRANQUICIA,
  NOMBRE_TIPO,
  pasaLuhn,
  soloDigitos,
  tarjetaVencida,
} from "./tarjeta";

describe("Reglas de tarjetas (RF-46, HU-28)", () => {
  it("valida el número con el algoritmo de Luhn", () => {
    expect(pasaLuhn("4242424242424242")).toBe(true);
    expect(pasaLuhn("4242 4242 4242 4242")).toBe(true);
    expect(pasaLuhn("5555555555554444")).toBe(true);
    expect(pasaLuhn("378282246310005")).toBe(true);
    expect(pasaLuhn("4242424242424241")).toBe(false);
    expect(pasaLuhn("")).toBe(false);
  });

  it("quita lo que no sea dígito y muestra el número en bloques de cuatro", () => {
    expect(soloDigitos("4242 4242-4242_4242")).toBe("4242424242424242");
    expect(agruparNumero("4242424242424242")).toBe("4242 4242 4242 4242");
    expect(agruparNumero("378282246310005")).toBe("3782 8224 6310 005");
  });

  // HU-28: la tarjeta vence al terminar su mes, en hora de Colombia.
  it("una tarjeta sirve hasta el último día de su mes de vencimiento", () => {
    const ahora = new Date("2026-11-16T12:00:00Z");
    expect(tarjetaVencida("11/26", ahora)).toBe(false);
    expect(tarjetaVencida("10/26", ahora)).toBe(true);
    expect(tarjetaVencida("01/27", ahora)).toBe(false);
    expect(tarjetaVencida("12/25", ahora)).toBe(true);
    expect(tarjetaVencida("08/28", ahora)).toBe(false);
    // Un formato inválido no se marca como vencido: lo rechaza la validación de formato.
    expect(tarjetaVencida("2028-08", ahora)).toBe(false);
  });

  it("nombra tipos y franquicias como se muestran en la interfaz", () => {
    expect(NOMBRE_TIPO.credito).toBe("Crédito");
    expect(NOMBRE_FRANQUICIA.visa).toBe("Visa");
    expect(NOMBRE_FRANQUICIA.mastercard).toBe("Mastercard");
  });
});
