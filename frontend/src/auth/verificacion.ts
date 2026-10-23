import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { PERFIL_KEY } from "./perfil";
import { SESION_KEY } from "./sesion";

/** Ruta del frontend a la que lleva el enlace del correo (`?token=…`). */
export const RUTA_VERIFICACION = "/verificar-correo";

/** Confirma el enlace del correo (HU-02). No exige sesión: el enlace puede abrirse en otro
 *  dispositivo. Si hay sesión, se vuelve a pedir el usuario para que `email_verificado` cambie. */
export function useVerificarCorreo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      unwrap(api.POST("/api/v1/usuarios/verificacion", { body: { token } })),
    onSuccess: async () => {
      // Si la sesión aún se estaba cargando cuando se confirmó el enlace, esa respuesta puede traer
      // el correo sin verificar: se descarta para que la consulta nueva salga después de verificar.
      await queryClient.cancelQueries({ queryKey: SESION_KEY });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: SESION_KEY }),
        queryClient.invalidateQueries({ queryKey: PERFIL_KEY }),
      ]);
    },
  });
}

/** Pide un enlace nuevo; el anterior deja de servir. */
export function useReenviarVerificacion() {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/usuarios/me/verificacion/reenviar")),
  });
}
