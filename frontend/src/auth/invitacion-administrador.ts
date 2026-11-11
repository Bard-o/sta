import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import { SESION_KEY } from "./sesion";

export const INVITACION_KEY = ["invitacion-administrador"] as const;

/** HU-12: comprueba el enlace de la invitación sin consumirlo. */
export function useValidarInvitacion(token: string | null) {
  return useQuery({
    queryKey: [...INVITACION_KEY, token],
    queryFn: () => {
      if (!token) throw new Error("Falta el token de la invitación.");
      return unwrap(api.POST("/api/v1/administradores/invitacion/validar", { body: { token } }));
    },
    enabled: Boolean(token),
    retry: false,
    staleTime: Infinity,
  });
}

/** HU-12: completa el registro y deja abierta la sesión del administrador. */
export function useCompletarInvitacion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: Schemas["CompletarInvitacionEntrada"]) =>
      unwrap(api.POST("/api/v1/administradores/invitacion/completar", { body: datos })),
    onSuccess: (usuario) => {
      queryClient.setQueryData(SESION_KEY, usuario);
    },
  });
}
