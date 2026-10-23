import type { FieldPath } from "react-hook-form";
import { z } from "zod";
import { hoy } from "@/lib/persona";
import type { SerieEntrada, VueloEntrada } from "./api";

export const DIAS = [
  { value: "lun", label: "Lun", nombre: "lunes" },
  { value: "mar", label: "Mar", nombre: "martes" },
  { value: "mie", label: "Mié", nombre: "miércoles" },
  { value: "jue", label: "Jue", nombre: "jueves" },
  { value: "vie", label: "Vie", nombre: "viernes" },
  { value: "sab", label: "Sáb", nombre: "sábado" },
  { value: "dom", label: "Dom", nombre: "domingo" },
] as const;

type Dia = (typeof DIAS)[number]["value"];

/** Último día para programar: 12 meses desde hoy (SUP-37). */
export function maximoHasta(): string {
  const limite = new Date();
  limite.setMonth(limite.getMonth() + 12);
  return limite.toLocaleDateString("sv-SE");
}

const entero = (min: number, max: number, mensaje: string) =>
  z
    .string()
    .trim()
    .transform((s) => (s === "" ? "0" : s))
    .pipe(z.string().regex(/^\d+$/, mensaje))
    .transform(Number)
    .pipe(z.number().min(min, mensaje).max(max, mensaje));

const precio = (mensaje: string) =>
  z
    .string()
    .transform((s) => s.replace(/\D/g, ""))
    .pipe(z.string().min(1, mensaje))
    .transform(Number)
    .pipe(z.number().min(1, "El precio debe ser mayor que 0."));

export const esquema = z
  .object({
    origen: z.string().min(1, "Elige la ciudad de origen."),
    destino: z.string().min(1, "Elige la ciudad de destino."),
    fecha_salida: z.string(),
    hora_salida: z.string().regex(/^\d{2}:\d{2}$/, "Escribe la hora de salida, por ejemplo 06:00."),
    horas: entero(0, 23, "Las horas van de 0 a 23."),
    minutos: entero(0, 59, "Los minutos van de 0 a 59."),
    precio_economica: precio("Escribe el precio de económica, en pesos."),
    precio_primera: precio("Escribe el precio de primera, en pesos."),
    repite: z.boolean(),
    dias: z.array(z.enum(DIAS.map((d) => d.value))),
    desde: z.string(),
    hasta: z.string(),
  })
  .superRefine((d, ctx) => {
    const error = (path: string, message: string) =>
      ctx.addIssue({ code: "custom", path: [path], message });

    if (d.origen && d.origen === d.destino)
      error("destino", "El destino debe ser distinto del origen.");
    const total = d.horas * 60 + d.minutos;
    if (total < 1 || total > 1439) {
      error("horas", "La duración debe ser de más de 0 minutos y menos de 24 horas.");
    }

    if (!d.repite) {
      if (!d.fecha_salida) error("fecha_salida", "Escribe la fecha de salida.");
      else if (d.fecha_salida < hoy())
        error("fecha_salida", "La fecha de salida no puede ser pasada.");
      return;
    }
    if (d.dias.length === 0) error("dias", "Elige al menos un día de la semana.");
    if (!d.desde) error("desde", "Escribe desde qué fecha se repite.");
    if (!d.hasta) error("hasta", "Escribe hasta qué fecha se repite.");
    else if (d.desde && d.hasta < d.desde) {
      error("hasta", "La fecha final no puede ser anterior a la inicial.");
    } else if (d.hasta > maximoHasta()) {
      error("hasta", "Máximo 12 meses desde hoy.");
    }
  });

export type Entrada = z.input<typeof esquema>;
export type Datos = z.output<typeof esquema>;

export const VACIO: Entrada = {
  origen: "",
  destino: "",
  fecha_salida: "",
  hora_salida: "",
  horas: "",
  minutos: "0",
  precio_economica: "",
  precio_primera: "",
  repite: false,
  dias: [],
  desde: "",
  hasta: "",
};

/** Campo del servidor → campo del formulario (la duración se escribe en horas y minutos). */
export const CAMPOS_API: Record<string, FieldPath<Entrada>> = {
  origen: "origen",
  destino: "destino",
  fecha_salida: "fecha_salida",
  hora_salida: "hora_salida",
  duracion_minutos: "horas",
  precio_economica: "precio_economica",
  precio_primera: "precio_primera",
  dias_semana: "dias",
  desde: "desde",
  hasta: "hasta",
};

type Base = Omit<VueloEntrada, "fecha_salida">;

const base = (d: Datos): Base => ({
  origen: d.origen,
  destino: d.destino,
  hora_salida: d.hora_salida,
  duracion_minutos: d.horas * 60 + d.minutos,
  precio_economica: d.precio_economica,
  precio_primera: d.precio_primera,
});

export const aEntradaApi = (d: Datos): VueloEntrada => ({
  ...base(d),
  fecha_salida: d.fecha_salida,
});

export const aSerieApi = (d: Datos): SerieEntrada => ({
  ...base(d),
  dias_semana: d.dias as Dia[],
  desde: d.desde,
  hasta: d.hasta,
});
