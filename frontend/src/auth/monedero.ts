// API del monedero de la iteración 2 (HU-28 a HU-31): tarjetas y recargas.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, unwrap, type Schemas } from "@/api/client";

export const CLAVE_MONEDERO = ["monedero"] as const;
export const CLAVE_TARJETAS = ["monedero", "tarjetas"] as const;
export const CLAVE_MOVIMIENTOS = ["monedero", "movimientos"] as const;

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

export type FiltrosMovimientos = {
  tipo: "recarga" | "compra" | "reembolso" | "";
  desde: string;
  hasta: string;
  pagina: number;
};

export const MOVIMIENTOS_POR_PAGINA = 20;

/** Movimientos del monedero, del más reciente al más antiguo (HU-31). Las fechas son del
 *  movimiento en hora de Colombia. Con `habilitado = false` (un rango que la pantalla ya ve
 *  inválido) no consulta. */
export function useMovimientos(filtros: FiltrosMovimientos, habilitado = true) {
  const query = {
    tipo: filtros.tipo || undefined,
    desde: filtros.desde || undefined,
    hasta: filtros.hasta || undefined,
    pagina: filtros.pagina,
    por_pagina: MOVIMIENTOS_POR_PAGINA,
  };
  return useQuery({
    queryKey: [...CLAVE_MOVIMIENTOS, query],
    enabled: habilitado,
    placeholderData: (anterior) => anterior,
    queryFn: () => unwrap(api.GET("/api/v1/monedero/movimientos", { params: { query } })),
  });
}

/** Elimina una tarjeta (borrado lógico, HU-29): deja de aparecer y de servir para recargar, y
 *  las recargas hechas con ella conservan su referencia. Se vuelve a leer el listado aunque
 *  falle: si ya se había eliminado en otra pestaña (`404`), la lista que quedó en pantalla está
 *  vieja. */
export function useEliminarTarjeta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tarjetaId: number) =>
      unwrap(
        api.DELETE("/api/v1/monedero/tarjetas/{tarjeta_id}", {
          params: { path: { tarjeta_id: tarjetaId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: CLAVE_TARJETAS }),
  });
}
