import { z } from "zod";
import type { Schemas } from "@/api/client";

export type TipoDocumento = Schemas["RegistroClienteEntrada"]["tipo_documento"];
export type Genero = Schemas["RegistroClienteEntrada"]["genero"];

export const TIPOS_DOCUMENTO: { value: TipoDocumento; label: string }[] = [
  { value: "CC", label: "Cédula de ciudadanía" },
  { value: "TI", label: "Tarjeta de identidad" },
  { value: "RC", label: "Registro civil" },
  { value: "CE", label: "Cédula de extranjería" },
  { value: "PA", label: "Pasaporte" },
];

export const GENEROS: { value: Genero; label: string }[] = [
  { value: "femenino", label: "Femenino" },
  { value: "masculino", label: "Masculino" },
  { value: "otro", label: "Otro" },
];

export const nombreTipoDocumento = (tipo: TipoDocumento) =>
  TIPOS_DOCUMENTO.find((t) => t.value === tipo)?.label ?? tipo;

/** Hoy como aaaa-mm-dd en la hora local de quien usa la pantalla. */
export const hoy = () => new Date().toLocaleDateString("sv-SE");

/** SUP-43: la fecha de nacimiento no puede ser de hace más de 120 años. */
export const EDAD_MAXIMA_ANOS = 120;
export const MENSAJE_EDAD_MAXIMA = "Revisa la fecha: la edad máxima es 120 años.";

const esBisiesto = (anio: number) => (anio % 4 === 0 && anio % 100 !== 0) || anio % 400 === 0;

/** Fecha de nacimiento más antigua aceptada, como aaaa-mm-dd: quien nació ese día cumple hoy
 *  exactamente 120 años (SUP-43). Si hoy es 29 de febrero y ese año no fue bisiesto, quien nació
 *  el 28 cumplió 120 ayer, así que la mínima es el 1 de marzo. Usa solo aritmética, sin `Date`,
 *  para no depender de la zona horaria. */
export function fechaMinimaNacimiento(hoyIso: string = hoy()): string {
  const [anio, mes, dia] = hoyIso.split("-").map(Number);
  const anioMinimo = anio - EDAD_MAXIMA_ANOS;
  const ajustar = mes === 2 && dia === 29 && !esBisiesto(anioMinimo);
  const mesMinimo = ajustar ? 3 : mes;
  const diaMinimo = ajustar ? 1 : dia;
  return [
    String(anioMinimo).padStart(4, "0"),
    String(mesMinimo).padStart(2, "0"),
    String(diaMinimo).padStart(2, "0"),
  ].join("-");
}

export const requerido = (mensaje: string, max = 200) =>
  z.string().trim().min(1, mensaje).max(max, `Usa como máximo ${max} caracteres.`);

/** Nombres y apellidos: deben tener letras; no se aceptan solo números o símbolos. */
const nombrePropio = (mensaje: string) =>
  requerido(mensaje, 100).regex(
    /^($|\p{L}[\p{L} '.-]*$)/u,
    "Usa solo letras, espacios, apóstrofo o guion.",
  );

/** Teléfono opcional: 7 a 20 dígitos, espacios, +, paréntesis o guiones, con al menos 7 dígitos. */
export const telefono = z
  .string()
  .trim()
  .refine((v) => v === "" || (/^[0-9 +()-]{7,20}$/.test(v) && (v.match(/\d/g) ?? []).length >= 7), {
    message: "Escribe un teléfono válido, con al menos 7 números.",
  });

/** Campos que comparten el registro (HU-01) y el perfil (HU-07), con sus mensajes (IU-07). */
export const camposPersona = {
  genero: z.string().refine((v): v is Genero => GENEROS.some((g) => g.value === v), {
    message: "Elige tu género.",
  }),
  nombres: nombrePropio("Escribe tus nombres."),
  apellidos: nombrePropio("Escribe tus apellidos."),
  fecha_nacimiento: requerido("Escribe tu fecha de nacimiento.")
    .refine((v) => v <= hoy(), {
      message: "La fecha de nacimiento no puede ser futura.",
    })
    .refine((v) => v === "" || v >= fechaMinimaNacimiento(), { message: MENSAJE_EDAD_MAXIMA }),
  lugar_nacimiento: requerido("Escribe tu lugar de nacimiento.", 120),
  direccion_facturacion: requerido("Escribe tu dirección de facturación."),
  email: z
    .string()
    .trim()
    .max(254)
    .pipe(z.email("Escribe un correo válido, por ejemplo nombre@correo.co.")),
};
