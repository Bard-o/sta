import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

export const PERFIL_KEY = ["perfil"] as const;

/** Perfil completo de la sesión (cliente o administrador). `habilitado` evita pedirlo sin sesión. */
export function usePerfil(habilitado = true) {
  return useQuery({
    queryKey: PERFIL_KEY,
    queryFn: () => unwrap(api.GET("/api/v1/usuarios/me/perfil")),
    enabled: habilitado,
  });
}
