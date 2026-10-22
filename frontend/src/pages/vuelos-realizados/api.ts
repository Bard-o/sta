import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

/** Pasajeros y ocupación de un vuelo (HU-18). Sin `vueloId` no consulta. */
export function usePasajerosVuelo(vueloId: number | null) {
  return useQuery({
    queryKey: ["vuelos", "pasajeros", vueloId],
    enabled: vueloId !== null,
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/vuelos/{vuelo_id}/pasajeros", {
          params: { path: { vuelo_id: vueloId as number } },
        }),
      ),
  });
}
