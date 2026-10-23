import { api, unwrap } from "@/api/client";

export const IMAGEN_TIPOS = ["image/jpeg", "image/png"];
export const IMAGEN_MAX_BYTES = 2 * 1024 * 1024;

/** Mensaje en español si el archivo no sirve como imagen de perfil (JPG o PNG, máximo 2 MB). */
export function validarImagen(archivo: File): string | null {
  if (!IMAGEN_TIPOS.includes(archivo.type)) return "La imagen debe ser JPG o PNG.";
  if (archivo.size > IMAGEN_MAX_BYTES) return "La imagen pesa más de 2 MB. Elige una más liviana.";
  return null;
}

/** Sube o reemplaza la imagen de perfil de la sesión (multipart/form-data, campo `imagen`). */
export function subirImagenPerfil(archivo: File) {
  return unwrap(
    api.PUT("/api/v1/usuarios/me/imagen", {
      body: { imagen: "" },
      // El esquema generado tipa el archivo como texto; el cuerpo real es un formulario multipart.
      bodySerializer: () => {
        const formulario = new FormData();
        formulario.append("imagen", archivo);
        return formulario;
      },
    }),
  );
}
