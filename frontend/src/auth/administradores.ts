import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export const ADMINISTRADORES_KEY = ["administradores"] as const;

/** Administradores con su estado, en el orden que entrega el servidor (HU-10, HU-11). */
export function useAdministradores() {
  return useQuery({
    queryKey: ADMINISTRADORES_KEY,
    queryFn: () => unwrap(api.GET("/api/v1/administradores")),
  });
}

/** Crea un administrador con usuario y contraseña temporal (HU-10). */
export function useCrearAdministrador() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: Schemas["AdministradorEntrada"]) =>
      unwrap(api.POST("/api/v1/administradores", { body: datos })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ADMINISTRADORES_KEY });
    },
  });
}

/** Desactiva un administrador (borrado lógico, HU-11). Se refresca también si el estado cambió
 *  en otro lado (`409 estado_invalido`) o el administrador ya no existe (`404`). */
export function useDesactivarAdministrador() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (adminId: number) =>
      unwrap(
        api.POST("/api/v1/administradores/{admin_id}/desactivar", {
          params: { path: { admin_id: adminId } },
        }),
      ),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ADMINISTRADORES_KEY });
    },
  });
}

/** Reactiva un administrador y devuelve su estado anterior: activo o registro incompleto (HU-11). */
export function useReactivarAdministrador() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (adminId: number) =>
      unwrap(
        api.POST("/api/v1/administradores/{admin_id}/reactivar", {
          params: { path: { admin_id: adminId } },
        }),
      ),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ADMINISTRADORES_KEY });
    },
  });
}
