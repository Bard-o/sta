import { useMutation, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

export const DESACTIVACION_KEY = ["desactivacion"] as const;

/** ¿Puede el cliente desactivar su cuenta? Si no, qué compras o reservas activas lo impiden. */
export function useEstadoDesactivacion() {
  return useQuery({
    queryKey: DESACTIVACION_KEY,
    queryFn: () => unwrap(api.GET("/api/v1/usuarios/me/desactivacion")),
  });
}

/** Desactiva la cuenta (borrado lógico, HU-09). El servidor cierra todas sus sesiones. */
export function useDesactivarCuenta() {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/usuarios/me/desactivacion")),
  });
}
