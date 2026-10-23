import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import type { VueloEntrada } from "../programar-vuelo/api";

export type VueloAdmin = Schemas["VueloAdmin"];

export const POR_PAGINA = 10;

export interface Filtros {
  q: string;
  desde: string;
  hasta: string;
  pagina: number;
}

/** Vuelos programados (S09): filtros por texto y por fechas de salida (hora de Colombia). */
export function useVuelosProgramados(filtros: Filtros, habilitado = true) {
  return useQuery({
    queryKey: ["vuelos", "admin", "programado", filtros],
    enabled: habilitado,
    placeholderData: (anterior) => anterior,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/vuelos", {
          params: {
            query: {
              estado: "programado",
              q: filtros.q || null,
              desde: filtros.desde || null,
              hasta: filtros.hasta || null,
              pagina: filtros.pagina,
              por_pagina: POR_PAGINA,
            },
          },
        }),
      ),
  });
}

/** Un vuelo con lo que hace falta para editarlo o cancelarlo (`editable`, `cancelable`…). */
export function useVueloGestion(vueloId: number) {
  return useQuery({
    queryKey: ["vuelos", "gestion", vueloId],
    enabled: Number.isInteger(vueloId) && vueloId > 0,
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/vuelos/{vuelo_id}/gestion", { params: { path: { vuelo_id: vueloId } } }),
      ),
  });
}

/** HU-15: guarda el vuelo completo; el servidor vuelve a validar y conserva el código. */
export function useEditarVuelo(vueloId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: VueloEntrada) =>
      unwrap(
        api.PUT("/api/v1/vuelos/{vuelo_id}", {
          params: { path: { vuelo_id: vueloId } },
          body: datos,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vuelos"] });
      void queryClient.invalidateQueries({ queryKey: ["noticias"] });
    },
  });
}

/** HU-16: cancela un vuelo sin tiquetes vendidos y anula sus reservas activas. */
export function useCancelarVuelo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vueloId: number) =>
      unwrap(
        api.POST("/api/v1/vuelos/{vuelo_id}/cancelar", {
          params: { path: { vuelo_id: vueloId } },
        }),
      ),
    // Con error (p. ej. el vuelo ya vendió un tiquete) se refresca igual: la fila cambió.
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["vuelos"] });
      void queryClient.invalidateQueries({ queryKey: ["noticias"] });
    },
  });
}
