// Reglas de la iteración 2 que la API simulada aplica igual que el backend
// (docs/api/iteracion-2.md). Funciones puras: no tocan el estado de los mocks.
import type { Schemas } from "@/api/client";
import { aIso } from "./tiempo";

type VueloAdmin = Schemas["VueloAdmin"];
export type Clase = "economica" | "primera";

// RNF-23: en el backend saldrán de la configuración.
export const MAX_TIQUETES = 5;
export const VIGENCIA_RESERVA_MIN = 24 * 60;
export const BLOQUEO_COMPRA_MIN = 15;
export const ZONA_COLOMBIA = "America/Bogota";
export const NOMBRE_CLASE: Record<Clase, string> = { economica: "económica", primera: "primera" };

/** SUP-07, RF-36: la venta cierra 1 h antes de la salida (3 h si es internacional). */
export function limiteDeVenta(v: Pick<VueloAdmin, "tipo" | "salida">): number {
  const horas = v.tipo === "nacional" ? 1 : 3;
  return Date.parse(v.salida) - horas * 3_600_000;
}

export function aLaVenta(v: VueloAdmin, ahora = Date.now()): boolean {
  return v.estado === "programado" && ahora < limiteDeVenta(v);
}

/** Vencimiento de una reserva (24 h) o de un bloqueo (15 min), o el límite de venta más próximo. */
export function venceEn(vuelos: VueloAdmin[], minutos: number, ahora = Date.now()): string {
  return aIso(new Date(Math.min(ahora + minutos * 60_000, ...vuelos.map(limiteDeVenta))));
}

/** Fecha aaaa-mm-dd de un instante en una zona. */
export function fechaLocal(iso: string, zona: string): string {
  return new Date(iso).toLocaleDateString("sv-SE", { timeZone: zona });
}

/** Hora hh:mm de un instante en una zona. */
export function horaLocal(iso: string, zona: string): string {
  return new Date(iso).toLocaleTimeString("sv-SE", {
    timeZone: zona,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

export const hoyEnColombia = () => fechaLocal(new Date().toISOString(), ZONA_COLOMBIA);

/** RF-35: años cumplidos el día `fecha`, como reservas.service.validar_menores. */
export function edadEn(nacimiento: string, fecha: string): number {
  const [an, mn, dn] = nacimiento.split("-").map(Number);
  const [a, m, d] = fecha.split("-").map(Number);
  return a - an - (m < mn || (m === mn && d < dn) ? 1 : 0);
}

/** RF-46: algoritmo de Luhn. */
export function pasaLuhn(numero: string): boolean {
  let suma = 0;
  [...numero].reverse().forEach((c, i) => {
    let n = Number(c);
    if (i % 2 === 1) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    suma += n;
  });
  return suma % 10 === 0;
}

export function franquiciaDe(numero: string): Schemas["Tarjeta"]["franquicia"] {
  const cuatro = Number(numero.slice(0, 4));
  if (/^4/.test(numero)) return "visa";
  if (/^5[1-5]/.test(numero) || (cuatro >= 2221 && cuatro <= 2720)) return "mastercard";
  if (/^3[47]/.test(numero)) return "amex";
  if (/^3(0[0-5]|[68])/.test(numero)) return "diners";
  return "otra";
}

/** La tarjeta sirve hasta el último día de su mes de vencimiento (MM/AA), en hora de Colombia. */
export function tarjetaVencida(mmaa: string, ahora = new Date()): boolean {
  const [mes, anio] = mmaa.split("/").map(Number);
  const [a, m] = fechaLocal(ahora.toISOString(), ZONA_COLOMBIA).split("-").map(Number);
  return 2000 + anio < a || (2000 + anio === a && mes < m);
}

/** Primer número interno de la clase (Apéndice A). */
export function primeraSilla(tipo: VueloAdmin["tipo"], clase: Clase): number {
  if (clase === "primera") return 1;
  return tipo === "nacional" ? 26 : 51;
}

/** Fila y letra de una silla (Apéndice A, SUP-26), como vuelos.service.nombre_de_silla. */
export function nombreDeSilla(tipo: VueloAdmin["tipo"], clase: Clase, numero: number): string {
  if (tipo === "internacional" && clase === "economica") {
    const m = numero - 50;
    return `${10 + Math.ceil(m / 10)}${"ABCDEFGHJK"[(m - 1) % 10]}`;
  }
  return `${Math.ceil(numero / 5)}${"ABCDE"[(numero - 1) % 5]}`;
}

const LETRAS_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

/** Código de reserva: 6 caracteres sin O, I, 0 ni 1. */
export function nuevoCodigo(): string {
  return Array.from(
    { length: 6 },
    () => LETRAS_CODIGO[Math.floor(Math.random() * LETRAS_CODIGO.length)],
  ).join("");
}
