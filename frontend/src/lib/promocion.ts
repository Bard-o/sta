/** Desfase fijo de Colombia: no tiene horario de verano (SUP-32). */
const DESFASE_COLOMBIA = "-05:00";

/** Precio con descuento: `floor(precio × (100 − porcentaje) / 100)`, en pesos enteros (RF-24). */
export function precioConDescuento(precio: number, porcentaje: number): number {
  return Math.floor((precio * (100 - porcentaje)) / 100);
}

/** «2026-10-15T10:00» (hora de Colombia, como la entrega un `datetime-local`) → ISO 8601 con
 *  desfase, que es lo que espera la API. */
export function aIsoColombia(local: string): string {
  return `${local}:00${DESFASE_COLOMBIA}`;
}

/** Instante de un `datetime-local` escrito en hora de Colombia, o NaN si no es válido. */
export const instanteColombia = (local: string): number =>
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local) ? Date.parse(aIsoColombia(local)) : NaN;
