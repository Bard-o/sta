import { patronDias, resumenSerie } from "./resumen";

describe("patronDias", () => {
  it("nombra los días elegidos en orden de calendario", () => {
    expect(patronDias(["vie", "lun"])).toBe("los lunes y viernes");
    expect(patronDias(["lun", "mie", "sab"])).toBe("los lunes, miércoles y sábados");
    expect(patronDias(["dom"])).toBe("los domingos");
  });

  it("los 7 días son «todos los días»", () => {
    expect(patronDias(["lun", "mar", "mie", "jue", "vie", "sab", "dom"])).toBe("todos los días");
  });
});

describe("resumenSerie", () => {
  it("cuenta los vuelos y agrupa las fechas omitidas por motivo", () => {
    const omitidas = [
      { fecha: "2026-10-05", codigo: "salida_en_pasado", motivo: "La salida ya pasó." },
      { fecha: "2026-12-07", codigo: "vuelo_duplicado", motivo: "Ya existe un vuelo igual." },
      { fecha: "2026-12-14", codigo: "vuelo_duplicado", motivo: "Ya existe un vuelo igual." },
    ] as const;
    expect(resumenSerie(12, [...omitidas], ["lun"])).toBe(
      "12 vuelos los lunes. 2 fechas omitidas porque ya existe un vuelo igual. 1 fecha omitida porque su salida ya pasó.",
    );
  });

  it("usa el singular y no menciona omitidas si no hay", () => {
    expect(resumenSerie(1, [], ["lun"])).toBe("1 vuelo los lunes.");
  });
});
