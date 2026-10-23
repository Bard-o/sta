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

export const requerido = (mensaje: string) => z.string().trim().min(1, mensaje);

/** Campos que comparten el registro (HU-01) y el perfil (HU-07), con sus mensajes (IU-07). */
export const camposPersona = {
  genero: z.string().refine((v): v is Genero => GENEROS.some((g) => g.value === v), {
    message: "Elige tu género.",
  }),
  nombres: requerido("Escribe tus nombres."),
  apellidos: requerido("Escribe tus apellidos."),
  fecha_nacimiento: requerido("Escribe tu fecha de nacimiento.").refine((v) => v <= hoy(), {
    message: "La fecha de nacimiento no puede ser futura.",
  }),
  lugar_nacimiento: requerido("Escribe tu lugar de nacimiento."),
  direccion_facturacion: requerido("Escribe tu dirección de facturación."),
  email: z.string().trim().pipe(z.email("Escribe un correo válido, por ejemplo nombre@correo.co.")),
};
