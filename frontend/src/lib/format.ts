// Formatos fijos de DESIGN.md (IU-05, IU-06).

/** Pesos colombianos: «$ 1.250.000». Con `sign`: «+ $ 500.000» / «− $ 800.000». */
export function cop(n: number, opts: { sign?: boolean } = {}): string {
  // Sin Intl a propósito: en español, Intl no agrupa los números de 4 cifras (1000, no 1.000).
  const entero = String(Math.abs(Math.round(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const valor = `$ ${entero}`;
  if (opts.sign) return `${n < 0 ? "−" : "+"} ${valor}`;
  return n < 0 ? `− ${valor}` : valor;
}

const dos = (n: number) => String(n).padStart(2, "0");

/** Fecha dd/mm/aaaa en la zona horaria dada (por defecto, la del navegador). */
export function fecha(iso: string | Date, timeZone?: string): string {
  const partes = new Intl.DateTimeFormat("es-CO", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone,
  }).formatToParts(new Date(iso));
  const p = (tipo: string) => partes.find((x) => x.type === tipo)?.value ?? "";
  return `${p("day")}/${p("month")}/${p("year")}`;
}

/** Hora de 24 h «15:00» en la zona horaria dada. */
export function hora(iso: string | Date, timeZone?: string): string {
  const partes = new Intl.DateTimeFormat("es-CO", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  }).formatToParts(new Date(iso));
  const p = (tipo: string) => Number(partes.find((x) => x.type === tipo)?.value ?? 0);
  return `${dos(p("hour"))}:${dos(p("minute"))}`;
}

/** Zona horaria de Colombia: toda la interfaz muestra «hoy» y «ayer» en esta hora (SUP-32). */
export const ZONA_COLOMBIA = "America/Bogota";

/** Fecha y hora «10/12/2026 15:00» en la zona dada. */
export function fechaHora(iso: string | Date, timeZone?: string): string {
  return `${fecha(iso, timeZone)} ${hora(iso, timeZone)}`;
}

/** Desfase de la zona respecto de UTC en ese instante: «UTC-5», «UTC+2», «UTC+5:30», o «UTC». */
export function desfase(iso: string | Date, timeZone: string): string {
  const nombre =
    new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "shortOffset" })
      .formatToParts(new Date(iso))
      .find((x) => x.type === "timeZoneName")?.value ?? "GMT";
  const m = /^GMT([+-])(\d{1,2})(?::(\d{2}))?$/.exec(nombre);
  // Según la versión de ICU, el desfase cero llega como «GMT» o como «GMT+0».
  if (!m || (Number(m[2]) === 0 && !m[3])) return "UTC";
  return `UTC${m[1]}${Number(m[2])}${m[3] ? `:${m[3]}` : ""}`;
}

/** «Hoy, 09:12», «Ayer, 16:40» o «27/09/2026», en hora de Colombia (wireframe S13). */
export function fechaRelativa(iso: string | Date, ahora: Date = new Date()): string {
  const dia = fecha(iso, ZONA_COLOMBIA);
  if (dia === fecha(ahora, ZONA_COLOMBIA)) return `Hoy, ${hora(iso, ZONA_COLOMBIA)}`;
  // Colombia no tiene horario de verano: restar 24 h siempre cae en el día anterior.
  if (dia === fecha(new Date(ahora.getTime() - 24 * 60 * 60 * 1000), ZONA_COLOMBIA)) {
    return `Ayer, ${hora(iso, ZONA_COLOMBIA)}`;
  }
  return dia;
}

/** Duración legible: «10 h», «50 min» o «1 h 30 min». */
export function duracion(minutos: number): string {
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return m === 0 ? `${h} h` : h === 0 ? `${m} min` : `${h} h ${m} min`;
}
