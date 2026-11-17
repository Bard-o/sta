// API del monedero de la iteración 2 (HU-28 a HU-31): tarjetas y recargas.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, unwrap, type Schemas } from "@/api/client";

export const CLAVE_MONEDERO = ["monedero"] as const;
export const CLAVE_TARJETAS = ["monedero", "tarjetas"] as const;

/** Tarjetas registradas y no eliminadas, de la más reciente a la más antigua (HU-29). */
export function useTarjetas() {
  return useQuery({
    queryKey: CLAVE_TARJETAS,
    queryFn: () => unwrap(api.GET("/api/v1/monedero/tarjetas")),
  });
}

/** RNF-12: el número y el CVV no pasan por la caché de mutaciones de TanStack Query. */
export async function registrarTarjeta(
  datos: Schemas["TarjetaEntrada"],
): Promise<Schemas["Tarjeta"]> {
  return unwrap(api.POST("/api/v1/monedero/tarjetas", { body: datos }));
}

/** Recarga aprobada de forma simulada si la tarjeta está vigente (HU-30, RF-47). */
export function useRecargar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: Schemas["RecargaEntrada"]) =>
      unwrap(api.POST("/api/v1/monedero/recargas", { body: datos })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CLAVE_MONEDERO }),
    // Si la tarjeta se eliminó en otra pestaña, el listado que quedó en pantalla está viejo.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 404) {
        void queryClient.invalidateQueries({ queryKey: CLAVE_TARJETAS });
      }
    },
  });
}
