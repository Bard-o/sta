// Reglas de las tarjetas simuladas (RF-46, RNF-12) y sus nombres para la interfaz.
import type { Schemas } from "@/api/client";
import { ZONA_COLOMBIA } from "./format";

/** Solo los dígitos de lo escrito: quita espacios, guiones y cualquier otro carácter. */
export function soloDigitos(texto: string): string {
  return texto.replace(/\D/g, "");
}

/** El número como se muestra: bloques de cuatro dígitos («4242 4242 4242 4242»). */
export function agruparNumero(numero: string): string {
  return soloDigitos(numero).replace(/(\d{4})(?=\d)/g, "$1 ");
}

/** RF-46: algoritmo de Luhn. */
export function pasaLuhn(numero: string): boolean {
  const digitos = soloDigitos(numero);
  if (digitos === "") return false;
  let suma = 0;
  [...digitos].reverse().forEach((caracter, indice) => {
    let digito = Number(caracter);
    if (indice % 2 === 1) digito *= 2;
    if (digito > 9) digito -= 9;
    suma += digito;
  });
  return suma % 10 === 0;
}

const FORMATO_VENCIMIENTO = /^(0[1-9]|1[0-2])\/\d{2}$/;

/** El vencimiento viaja como MM/AA (contrato de HU-28). */
export function formatoVencimientoValido(mmaa: string): boolean {
  return FORMATO_VENCIMIENTO.test(mmaa);
}

/** Mes y año actuales en hora de Colombia: el vencimiento rige todo ese mes. */
function mesActual(ahora: Date): { mes: number; anio: number } {
  const partes = new Intl.DateTimeFormat("es-CO", {
    timeZone: ZONA_COLOMBIA,
    year: "numeric",
    month: "2-digit",
  }).formatToParts(ahora);
  const valor = (tipo: Intl.DateTimeFormatPartTypes) =>
    Number(partes.find((parte) => parte.type === tipo)?.value ?? 0);
  return { mes: valor("month"), anio: valor("year") };
}

/** Una tarjeta sirve hasta el último día de su mes de vencimiento (MM/AA), en hora de Colombia. */
export function tarjetaVencida(mmaa: string, ahora: Date = new Date()): boolean {
  if (!formatoVencimientoValido(mmaa)) return false;
  const [mes, anio] = mmaa.split("/").map(Number);
  const actual = mesActual(ahora);
  return 2000 + anio < actual.anio || (2000 + anio === actual.anio && mes < actual.mes);
}

export const NOMBRE_TIPO: Record<Schemas["Tarjeta"]["tipo"], string> = {
  credito: "Crédito",
  debito: "Débito",
};

export const NOMBRE_FRANQUICIA: Record<Schemas["Tarjeta"]["franquicia"], string> = {
  visa: "Visa",
  mastercard: "Mastercard",
  amex: "American Express",
  diners: "Diners Club",
  otra: "Otra",
};
