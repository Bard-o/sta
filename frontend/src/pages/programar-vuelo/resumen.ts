import type { Schemas } from "@/api/client";
import { DIAS } from "./esquema";

/** «los lunes y viernes», «los lunes, miércoles y viernes» o «todos los días». */
export function patronDias(dias: readonly string[]): string {
  if (dias.length === DIAS.length) return "todos los días";
  const nombres = DIAS.filter((d) => dias.includes(d.value)).map((d) =>
    d.nombre.endsWith("s") ? d.nombre : `${d.nombre}s`,
  );
  const ultimo = nombres.pop();
  return `los ${nombres.length ? `${nombres.join(", ")} y ` : ""}${ultimo}`;
}

const plural = (n: number, uno: string, varios: string) => (n === 1 ? uno : varios);

/** «1 fecha omitida porque ya existe un vuelo igual.» (una frase por motivo). */
export function frasesOmitidas(omitidas: Schemas["FechaOmitida"][]): string[] {
  const motivos: [Schemas["FechaOmitida"]["codigo"], string][] = [
    ["vuelo_duplicado", "porque ya existe un vuelo igual"],
    ["salida_en_pasado", "porque su salida ya pasó"],
  ];
  return motivos.flatMap(([codigo, texto]) => {
    const n = omitidas.filter((o) => o.codigo === codigo).length;
    return n > 0 ? [`${n} ${plural(n, "fecha omitida", "fechas omitidas")} ${texto}.`] : [];
  });
}

/** «50 vuelos los lunes y viernes. 1 fecha omitida porque ya existe un vuelo igual.» */
export function resumenSerie(
  creados: number,
  omitidas: Schemas["FechaOmitida"][],
  dias: readonly string[],
): string {
  return [
    `${creados} ${plural(creados, "vuelo", "vuelos")} ${patronDias(dias)}.`,
    ...frasesOmitidas(omitidas),
  ].join(" ");
}
