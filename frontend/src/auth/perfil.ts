import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import { subirImagenPerfil } from "./imagen-perfil";
import { SESION_KEY } from "./sesion";

export const PERFIL_KEY = ["perfil"] as const;

/** Perfil completo de la sesión (cliente o administrador). `habilitado` evita pedirlo sin sesión. */
export function usePerfil(habilitado = true) {
  return useQuery({
    queryKey: PERFIL_KEY,
    queryFn: () => unwrap(api.GET("/api/v1/usuarios/me/perfil")),
    enabled: habilitado,
  });
}

type Perfil = Schemas["PerfilSalida"];

/** Guarda los datos editables del perfil (HU-07). Un correo distinto queda como pendiente hasta
 *  verificarlo. Actualiza el perfil y vuelve a pedir la sesión (el nombre sale en el menú). */
export function useGuardarPerfil() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: Schemas["PerfilEntrada"]) =>
      unwrap(api.PUT("/api/v1/usuarios/me/perfil", { body: datos })),
    onSuccess: (perfil) => {
      queryClient.setQueryData(PERFIL_KEY, perfil);
      void queryClient.invalidateQueries({ queryKey: SESION_KEY });
    },
  });
}

/** Sube o reemplaza la imagen de perfil. */
export function useSubirImagen() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: subirImagenPerfil,
    onSuccess: (perfil) => queryClient.setQueryData(PERFIL_KEY, perfil),
  });
}

/** Quita la imagen de perfil. */
export function useQuitarImagen() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/usuarios/me/imagen")),
    onSuccess: () =>
      queryClient.setQueryData<Perfil>(PERFIL_KEY, (perfil) =>
        perfil ? { ...perfil, imagen_url: null } : perfil,
      ),
  });
}

/** Cambia la contraseña con la actual (HU-06). La sesión sigue abierta. */
export function useCambiarContrasena() {
  return useMutation({
    mutationFn: (datos: Schemas["CambioContrasenaEntrada"]) =>
      unwrap(api.PUT("/api/v1/usuarios/me/contrasena", { body: datos })),
  });
}
