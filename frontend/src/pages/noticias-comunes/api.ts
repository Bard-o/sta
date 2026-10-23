import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

/** El carrusel muestra como máximo 10 elementos (HU-19, SUP-06). */
export const MAX_CARRUSEL = 10;
export const NOTICIAS_POR_PAGINA = 10;

export function useCarrusel() {
  return useQuery({
    queryKey: ["noticias", "carrusel"],
    queryFn: () => unwrap(api.GET("/api/v1/noticias/carrusel")),
  });
}

export function useNoticias(pagina: number, porPagina: number = NOTICIAS_POR_PAGINA) {
  return useQuery({
    queryKey: ["noticias", "lista", pagina, porPagina],
    queryFn: () =>
      unwrap(api.GET("/api/v1/noticias", { params: { query: { pagina, por_pagina: porPagina } } })),
    placeholderData: (anterior) => anterior,
  });
}

/** `vueloId` inválido (0, NaN) no consulta al servidor: la página muestra «no encontrada». */
export function useVueloDetalle(vueloId: number) {
  return useQuery({
    queryKey: ["vuelos", "detalle", vueloId],
    enabled: Number.isInteger(vueloId) && vueloId > 0,
    queryFn: () =>
      unwrap(api.GET("/api/v1/vuelos/{vuelo_id}", { params: { path: { vuelo_id: vueloId } } })),
    // Un 404 no se reintenta: el vuelo no existe.
    retry: false,
  });
}
