import { z } from "zod";
import {
  fechaMinimaNacimiento,
  GENEROS,
  hoy,
  MENSAJE_EDAD_MAXIMA,
  nombrePropio,
  requerido,
  TIPOS_DOCUMENTO,
  type TipoDocumento,
} from "@/lib/persona";

export type Clase = "economica" | "primera";
const CLASES: [Clase, ...Clase[]] = ["economica", "primera"];

const telefonoObligatorio = (mensaje: string) =>
  requerido(mensaje, 20).regex(
    /^[0-9 +()-]{7,20}$/,
    "Escribe un teléfono válido, con al menos 7 números.",
  );

/** Un viajero (RF-31): todos los datos son obligatorios, así cada viajero recibe su código de
 *  reserva. Los mensajes dicen qué está mal y cómo corregirlo (IU-07). */
export const esquemaViajero = z.object({
  tipo_documento: z
    .string()
    .refine((v): v is TipoDocumento => TIPOS_DOCUMENTO.some((t) => t.value === v), {
      message: "Elige el tipo de documento.",
    }),
  numero_documento: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9]{3,20}$/, "Usa de 3 a 20 letras o números, sin espacios ni puntos."),
  nombres: nombrePropio("Escribe los nombres del viajero."),
  apellidos: nombrePropio("Escribe los apellidos del viajero."),
  fecha_nacimiento: requerido("Escribe la fecha de nacimiento.")
    .refine((v) => v <= hoy(), { message: "La fecha de nacimiento no puede ser futura." })
    .refine((v) => v >= fechaMinimaNacimiento(), { message: MENSAJE_EDAD_MAXIMA }),
  genero: z.string().refine((v) => GENEROS.some((g) => g.value === v), {
    message: "Elige el género del viajero.",
  }),
  telefono: telefonoObligatorio("Escribe el teléfono del viajero."),
  email: z
    .string()
    .trim()
    .max(254)
    .pipe(z.email("Escribe un correo válido, por ejemplo nombre@correo.co.")),
  contacto_nombre: nombrePropio("Escribe el nombre del contacto de emergencia."),
  contacto_telefono: telefonoObligatorio("Escribe el teléfono del contacto de emergencia."),
  clases: z.array(z.enum(CLASES)).min(1),
});

export const esquema = z.object({ viajeros: z.array(esquemaViajero).min(1) });

export type Entrada = z.input<typeof esquema>;
export type Datos = z.output<typeof esquema>;
export type EntradaViajero = Entrada["viajeros"][number];

export const viajeroVacio = (clases: Clase[]): EntradaViajero => ({
  tipo_documento: "CC",
  numero_documento: "",
  nombres: "",
  apellidos: "",
  fecha_nacimiento: "",
  genero: "",
  telefono: "",
  email: "",
  contacto_nombre: "",
  contacto_telefono: "",
  clases,
});
