import { z } from "zod";

/** Política de contraseña (RNF-08): 8 caracteres o más, con al menos una letra y un número.
 *  Los mensajes dicen qué falta, para corregirlo junto al campo (IU-07). */
export const esquemaContrasena = z
  .string()
  .min(8, "La contraseña debe tener al menos 8 caracteres.")
  .regex(/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/, "La contraseña debe tener al menos una letra.")
  .regex(/\d/, "La contraseña debe tener al menos un número.");

export const AYUDA_CONTRASENA = "Mínimo 8 caracteres, con al menos una letra y un número.";
