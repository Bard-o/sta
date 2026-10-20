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
