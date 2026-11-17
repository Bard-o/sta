import { fechaCalendario } from "@/lib/format";

/** Los nueve criterios de HU-20 más el orden y la página. Se guardan en la dirección para poder
 *  recargar o compartir la búsqueda; `franja` es la franja horaria que se traduce a hora_desde y
 *  hora_hasta (la API solo conoce las horas). */
export const CLAVES_FILTRO = [
  "codigo",
  "origen",
  "destino",
  "tipo",
  "fecha_desde",
  "fecha_hasta",
  "franja",
  "duracion_min",
  "duracion_max",
  "precio_min",
  "precio_max",
  "clase",
] as const;

export type ClaveFiltro = (typeof CLAVES_FILTRO)[number];
export type Filtros = Record<ClaveFiltro, string>;

export const FILTROS_VACIOS: Filtros = Object.fromEntries(
  CLAVES_FILTRO.map((clave) => [clave, ""]),
) as Filtros;

export type Orden = "precio" | "fecha" | "duracion";
export const ORDENES: { value: Orden; label: string }[] = [
  { value: "precio", label: "Precio más bajo" },
  { value: "fecha", label: "Salida más próxima" },
  { value: "duracion", label: "Menor duración" },
];

/** Franjas del wireframe S14 en la hora local del origen. */
export const FRANJAS = [
  { value: "madrugada", label: "Madrugada (00:00 a 05:59)", desde: "00:00", hasta: "05:59" },
  { value: "manana", label: "Mañana (06:00 a 11:59)", desde: "06:00", hasta: "11:59" },
  { value: "tarde", label: "Tarde (12:00 a 17:59)", desde: "12:00", hasta: "17:59" },
  { value: "noche", label: "Noche (18:00 a 23:59)", desde: "18:00", hasta: "23:59" },
] as const;

export const NOMBRE_CLASE = { economica: "económica", primera: "primera clase" } as const;
export type Clase = keyof typeof NOMBRE_CLASE;

const TIPOS = ["nacional", "internacional"];

/** Lee los filtros de la dirección; un valor que no tiene sentido (clase o tipo desconocidos) se
 *  descarta para no pedirle al servidor algo que va a rechazar por formato. */
export function leerFiltros(params: URLSearchParams): Filtros {
  const filtros = { ...FILTROS_VACIOS };
  for (const clave of CLAVES_FILTRO) filtros[clave] = params.get(clave) ?? "";
  if (!TIPOS.includes(filtros.tipo)) filtros.tipo = "";
  if (filtros.clase !== "economica" && filtros.clase !== "primera") filtros.clase = "";
  if (!FRANJAS.some((f) => f.value === filtros.franja)) filtros.franja = "";
  return filtros;
}

export function leerOrden(params: URLSearchParams): Orden {
  const orden = params.get("orden");
  return ORDENES.some((o) => o.value === orden) ? (orden as Orden) : "precio";
}

export function leerPagina(params: URLSearchParams): number {
  return Math.max(1, Math.trunc(Number(params.get("pagina"))) || 1);
}

const entero = (valor: string) => {
  if (valor.trim() === "") return undefined;
  const n = Number(valor);
  return Number.isFinite(n) ? Math.trunc(n) : undefined;
};

/** Parámetros de `GET /busqueda/vuelos`: solo lo que tiene valor. */
export function aConsulta(filtros: Filtros, orden: Orden, pagina: number) {
  const franja = FRANJAS.find((f) => f.value === filtros.franja);
  return {
    codigo: filtros.codigo.trim() || undefined,
    origen: filtros.origen || undefined,
    destino: filtros.destino || undefined,
    tipo: (filtros.tipo || undefined) as "nacional" | "internacional" | undefined,
    fecha_desde: filtros.fecha_desde || undefined,
    fecha_hasta: filtros.fecha_hasta || undefined,
    hora_desde: franja?.desde,
    hora_hasta: franja?.hasta,
    duracion_min: entero(filtros.duracion_min),
    duracion_max: entero(filtros.duracion_max),
    precio_min: entero(filtros.precio_min),
    precio_max: entero(filtros.precio_max),
    clase: (filtros.clase || undefined) as Clase | undefined,
    orden,
    pagina,
    por_pagina: 20,
  };
}

/** Errores de rango que la pantalla detecta antes de enviar, con los textos del contrato
 *  (`rango_invalido`, HU-20). El servidor los vuelve a validar. */
export function validarRangos(filtros: Filtros): Partial<Record<ClaveFiltro, string>> {
  const errores: Partial<Record<ClaveFiltro, string>> = {};
  const [pMin, pMax] = [entero(filtros.precio_min), entero(filtros.precio_max)];
  if (pMin !== undefined && pMax !== undefined && pMax < pMin) {
    errores.precio_max = "Debe ser mayor o igual que el precio mínimo.";
  }
  const [dMin, dMax] = [entero(filtros.duracion_min), entero(filtros.duracion_max)];
  if (dMin !== undefined && dMax !== undefined && dMax < dMin) {
    errores.duracion_max = "Debe ser mayor o igual que la duración mínima.";
  }
  if (filtros.fecha_desde && filtros.fecha_hasta && filtros.fecha_hasta < filtros.fecha_desde) {
    errores.fecha_hasta = "La fecha final no puede ser anterior a la inicial.";
  }
  return errores;
}

export const hayFiltros = (filtros: Filtros) => CLAVES_FILTRO.some((c) => filtros[c] !== "");

/** «15/04/2027 al 18/04/2027, económica, mañana»: lo que se está buscando, para el subtítulo. */
export function resumenDeFiltros(filtros: Filtros, nombreCiudad: (codigo: string) => string) {
  const partes: string[] = [];
  if (filtros.destino) partes.push(`a ${nombreCiudad(filtros.destino)}`);
  if (filtros.fecha_desde && filtros.fecha_hasta) {
    partes.push(
      `${fechaCalendario(filtros.fecha_desde)} al ${fechaCalendario(filtros.fecha_hasta)}`,
    );
  } else if (filtros.fecha_desde) {
    partes.push(`desde el ${fechaCalendario(filtros.fecha_desde)}`);
  } else if (filtros.fecha_hasta) {
    partes.push(`hasta el ${fechaCalendario(filtros.fecha_hasta)}`);
  }
  if (filtros.clase) partes.push(NOMBRE_CLASE[filtros.clase as Clase]);
  const franja = FRANJAS.find((f) => f.value === filtros.franja);
  if (franja) partes.push(franja.value === "manana" ? "mañana" : franja.value);
  if (filtros.tipo) partes.push(filtros.tipo === "nacional" ? "nacionales" : "internacionales");
  return partes.join(", ");
}
