import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import { SESION_KEY, SESION_VENCIDA_KEY } from "./sesion";

/** Ruta del frontend a la que lleva el enlace del correo (`?token=…`). */
export const RUTA_RESTABLECER = "/restablecer-contrasena";

/** Paso 1 (HU-05): pide el enlace. La respuesta es la misma exista o no el correo (RF-07). */
export function useSolicitarRestablecimiento() {
  return useMutation({
    mutationFn: (email: string) =>
      unwrap(api.POST("/api/v1/auth/restablecimiento", { body: { email } })),
  });
}

/** Paso 2: define la contraseña nueva. El servidor cierra todas las sesiones del usuario, así que
 *  también se olvida la de este navegador, sin avisar de «sesión vencida». */
export function useConfirmarRestablecimiento() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: Schemas["RestablecimientoConfirmacion"]) =>
      unwrap(api.POST("/api/v1/auth/restablecimiento/confirmar", { body: datos })),
    onSuccess: () => {
      queryClient.setQueryData(SESION_VENCIDA_KEY, false);
      queryClient.setQueryData(SESION_KEY, null);
    },
  });
}
