import type { FieldPath } from "react-hook-form";
import { z } from "zod";
import { aIsoColombia, instanteColombia } from "@/lib/promocion";
import type { PromocionEntrada } from "./api";

export const CLASES = [
  { value: "economica", label: "Económica", nombre: "económica" },
  { value: "primera", label: "Primera", nombre: "primera" },
] as const;

export const nombreClase = (clase: "economica" | "primera") =>
  CLASES.find((c) => c.value === clase)?.label ?? clase;

/** Porcentaje entero de 1 % a 90 % (SUP-38). */
export const porcentajeValido = (texto: string): number | null => {
  if (!/^\d+$/.test(texto.trim())) return null;
  const n = Number(texto);
  return n >= 1 && n <= 90 ? n : null;
};

export const esquema = z
  .object({
    porcentaje: z.string().refine((v) => porcentajeValido(v) !== null, {
      message: "El porcentaje debe ser un número entero entre 1 y 90.",
    }),
    clases: z.array(z.enum(CLASES.map((c) => c.value))).min(1, "Elige al menos una clase."),
    inicio: z.string().min(1, "Escribe la fecha y la hora de inicio."),
    fin: z.string().min(1, "Escribe la fecha y la hora de fin."),
  })
  .superRefine((d, ctx) => {
    if (!d.inicio || !d.fin) return;
    if (instanteColombia(d.fin) <= instanteColombia(d.inicio)) {
      ctx.addIssue({
        code: "custom",
        path: ["fin"],
        message: "El fin debe ser posterior al inicio.",
      });
    } else if (instanteColombia(d.fin) <= Date.now()) {
      ctx.addIssue({ code: "custom", path: ["fin"], message: "El fin debe ser una fecha futura." });
    }
  });

export type Entrada = z.input<typeof esquema>;
export type Datos = z.output<typeof esquema>;

export const VACIO: Entrada = { porcentaje: "", clases: [], inicio: "", fin: "" };

export const CAMPOS_API: Record<string, FieldPath<Entrada>> = {
  porcentaje: "porcentaje",
  clases: "clases",
  inicio: "inicio",
  fin: "fin",
};

export const aEntradaApi = (d: Datos): PromocionEntrada => ({
  porcentaje: Number(d.porcentaje),
  clases: d.clases,
  inicio: aIsoColombia(d.inicio),
  fin: aIsoColombia(d.fin),
});
