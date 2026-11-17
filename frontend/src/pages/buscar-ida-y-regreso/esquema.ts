import { fechaCalendario } from "@/lib/format";

/** El trayecto completo se arma en la dirección: la búsqueda (ciudades y fechas) y lo elegido
 *  (vuelos y clases), para poder recargar, compartir o volver de iniciar sesión sin perder nada. */
export const CLAVES = [
  "origen",
  "destino",
  "regreso",
  "fecha_ida",
  "fecha_regreso",
  "viajeros",
  "ida",
  "clase_ida",
  "regreso_id",
  "clase_regreso",
] as const;
export type Clave = (typeof CLAVES)[number];
export type Parametros = Record<Clave, string>;

export type Clase = "economica" | "primera";
export const NOMBRE_CLASE: Record<Clase, string> = {
  economica: "económica",
  primera: "primera",
};

export const VACIOS: Parametros = Object.fromEntries(CLAVES.map((c) => [c, ""])) as Parametros;

const esClase = (v: string): v is Clase => v === "economica" || v === "primera";

export function leer(params: URLSearchParams): Parametros {
  const valores = { ...VACIOS };
  for (const clave of CLAVES) valores[clave] = params.get(clave) ?? "";
  if (!esClase(valores.clase_ida)) valores.clase_ida = "";
  if (!esClase(valores.clase_regreso)) valores.clase_regreso = "";
  const viajeros = Math.trunc(Number(valores.viajeros));
  valores.viajeros = viajeros >= 1 && viajeros <= 5 ? String(viajeros) : "1";
  return valores;
}

/** Los cinco datos de la búsqueda (HU-21). */
export const CAMPOS_BUSQUEDA = [
  "origen",
  "destino",
  "regreso",
  "fecha_ida",
  "fecha_regreso",
] as const;
export type CampoBusqueda = (typeof CAMPOS_BUSQUEDA)[number];
export type ErroresBusqueda = Partial<Record<CampoBusqueda, string>>;

export const busquedaCompleta = (p: Parametros) => CAMPOS_BUSQUEDA.every((c) => p[c] !== "");

/** Errores que la pantalla detecta antes de enviar, con los textos del contrato (HU-21). */
export function validarBusqueda(p: Parametros): ErroresBusqueda {
  const errores: ErroresBusqueda = {};
  if (!p.origen) errores.origen = "Elige la ciudad de salida.";
  if (!p.destino) errores.destino = "Elige la ciudad de destino.";
  else if (p.destino === p.origen) errores.destino = "El destino debe ser distinto de la salida.";
  if (!p.regreso) errores.regreso = "Elige la ciudad de regreso.";
  else if (p.regreso === p.destino)
    errores.regreso = "La ciudad de regreso debe ser distinta del destino.";
  if (!p.fecha_ida) errores.fecha_ida = "Elige la fecha de ida.";
  if (!p.fecha_regreso) errores.fecha_regreso = "Elige la fecha de regreso.";
  else if (p.fecha_ida && p.fecha_regreso < p.fecha_ida) {
    errores.fecha_regreso = "La fecha de regreso no puede ser anterior a la de ida.";
  }
  return errores;
}

/** «Ida el 17/10/2026 y regreso el 24/10/2026.» */
export const fechasDelTrayecto = (p: Parametros) =>
  `Ida el ${fechaCalendario(p.fecha_ida)} y regreso el ${fechaCalendario(p.fecha_regreso)}.`;
