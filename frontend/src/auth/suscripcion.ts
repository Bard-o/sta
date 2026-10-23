import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import { PERFIL_KEY } from "./perfil";

/** Ruta del frontend a la que lleva el enlace «cancelar suscripción» de cada correo de noticias. */
export const RUTA_BAJA_NOTICIAS = "/noticias/baja";

/** Se suscribe o se da de baja desde el perfil (HU-08). Suscribirse exige el correo verificado. */
export function useSuscripcion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noticias: boolean) =>
      unwrap(api.PUT("/api/v1/usuarios/me/suscripcion", { body: { noticias } })),
    onSuccess: ({ noticias }) =>
      queryClient.setQueryData<Schemas["PerfilSalida"]>(PERFIL_KEY, (perfil) =>
        perfil ? { ...perfil, suscrito_noticias: noticias } : perfil,
      ),
  });
}

/** Baja con el enlace del correo: no exige sesión y el token no vence. */
export function useBajaNoticias() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      unwrap(api.POST("/api/v1/usuarios/suscripcion/baja", { body: { token } })),
    // Si esta misma persona tiene la sesión abierta, su perfil ya no debe verse como suscrito.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PERFIL_KEY }),
  });
}
