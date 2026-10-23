import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export type Promocion = Schemas["Promocion"];
export type PromocionEntrada = Schemas["PromocionEntrada"];
export type EstadoPromocion = Promocion["estado"];

export const POR_PAGINA = 10;

/** Promociones de todos los vuelos, de la más reciente a la más antigua. */
export function usePromociones(estado: EstadoPromocion | "", pagina: number) {
  return useQuery({
    queryKey: ["promociones", estado, pagina],
    placeholderData: (anterior) => anterior,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/promociones", {
          params: { query: { estado: estado || null, pagina, por_pagina: POR_PAGINA } },
        }),
      ),
  });
}

/** HU-17: crea la promoción de un vuelo; el servidor publica su noticia (RF-25). */
export function useCrearPromocion(vueloId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: PromocionEntrada) =>
      unwrap(
        api.POST("/api/v1/vuelos/{vuelo_id}/promociones", {
          params: { path: { vuelo_id: vueloId } },
          body: datos,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["promociones"] });
      void queryClient.invalidateQueries({ queryKey: ["vuelos"] });
      void queryClient.invalidateQueries({ queryKey: ["noticias"] });
    },
  });
}
