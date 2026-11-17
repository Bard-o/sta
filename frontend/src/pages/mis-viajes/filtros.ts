import { ZONA_COLOMBIA } from "@/lib/format";
import type { EstadoReserva, TipoViaje } from "./api";

export const ESTADOS_RESERVA: { value: EstadoReserva | ""; label: string }[] = [
  { value: "", label: "Todas" },
  { value: "vigente", label: "Vigentes" },
  { value: "pagada", label: "Pagadas" },
  { value: "vencida", label: "Vencidas" },
  { value: "cancelada", label: "Canceladas" },
];

export const leerTipo = (params: URLSearchParams): TipoViaje =>
  params.get("tipo") === "compra" ? "compra" : "reserva";

export const leerEstado = (params: URLSearchParams): EstadoReserva | "" => {
  const estado = params.get("estado");
  return ESTADOS_RESERVA.some((e) => e.value === estado && e.value !== "")
    ? (estado as EstadoReserva)
    : "";
};

export const leerMes = (params: URLSearchParams): string =>
  /^\d{4}-(0[1-9]|1[0-2])$/.test(params.get("mes") ?? "") ? (params.get("mes") as string) : "";

export const leerPagina = (params: URLSearchParams): number =>
  Math.max(1, Math.trunc(Number(params.get("pagina"))) || 1);

/** Primer y último día del mes (`aaaa-mm`), o nada si no hay mes: es lo que manda el selector
 *  «Octubre de 2026» (HU-27). */
export function rangoDelMes(mes: string): { desde?: string; hasta?: string } {
  if (!mes) return {};
  const [anio, numero] = mes.split("-").map(Number);
  const ultimo = new Date(Date.UTC(anio, numero, 0)).getUTCDate();
  return { desde: `${mes}-01`, hasta: `${mes}-${String(ultimo).padStart(2, "0")}` };
}

const MESES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

export const nombreDelMes = (mes: string) => {
  const [anio, numero] = mes.split("-").map(Number);
  return `${MESES[numero - 1]} de ${anio}`;
};

/** Meses para el selector: desde 2 meses atrás hasta 14 adelante, con el día de hoy en Colombia
 *  (las reservas pueden ser de vuelos de los próximos meses). Un mes de la dirección que quede
 *  fuera se agrega para que el selector no lo pierda. */
export function opcionesDeMes(
  actual: string,
  hoy = new Date(),
): { value: string; label: string }[] {
  const [anio, mes] = hoy
    .toLocaleDateString("sv-SE", { timeZone: ZONA_COLOMBIA })
    .split("-")
    .map(Number);
  const meses: string[] = [];
  for (let i = -2; i <= 14; i++) {
    const indice = anio * 12 + (mes - 1) + i;
    meses.push(`${Math.floor(indice / 12)}-${String((indice % 12) + 1).padStart(2, "0")}`);
  }
  if (actual && !meses.includes(actual)) meses.push(actual);
  return [
    { value: "", label: "Todos los meses" },
    ...meses.sort().map((m) => ({ value: m, label: nombreDelMes(m) })),
  ];
}
