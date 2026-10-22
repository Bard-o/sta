import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap, type Schemas } from "@/api/client";
import type { Usuario } from "./roles";

export const SESION_KEY = ["sesion"] as const;
/** true cuando la sesión terminó porque una petición respondió 401 (RNF-14); el login lo avisa. */
export const SESION_VENCIDA_KEY = ["sesion-vencida"] as const;

/** Usuario de la sesión, o null si es un visitante. */
export function useSesion() {
  return useQuery({
    queryKey: SESION_KEY,
    queryFn: async (): Promise<Usuario | null> => {
      try {
        return await unwrap(api.GET("/api/v1/auth/me"));
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

/** ¿La sesión anterior venció por inactividad? Solo se activa si había una sesión abierta. */
export function useSesionVencida(): boolean {
  const { data } = useQuery({
    queryKey: SESION_VENCIDA_KEY,
    queryFn: () => false,
    initialData: false,
    staleTime: Infinity,
  });
  return data;
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: Schemas["LoginEntrada"]) =>
      unwrap(api.POST("/api/v1/auth/login", { body: datos })),
    onSuccess: (usuario) => {
      queryClient.setQueryData(SESION_VENCIDA_KEY, false);
      queryClient.setQueryData(SESION_KEY, usuario);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/logout")),
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(SESION_KEY, null);
    },
  });
}
