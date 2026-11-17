import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export type ViajeEntrada = Schemas["ViajeEntrada"];
export type ViajeroEntrada = Schemas["ViajeroEntrada"];
export type Viaje = Schemas["Viaje"];

/** Reserva sin pagar (HU-24): bloquea las sillas y congela el precio hasta `vence_en`. */
export function useReservar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (viaje: ViajeEntrada) => unwrap(api.POST("/api/v1/reservas", { body: viaje })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["mis-viajes"] });
    },
  });
}

/** Inicia una compra (HU-25): asigna y bloquea las sillas 15 minutos; el cobro es otro paso
 *  (`POST /compras/{id}/confirmar`, #134). */
export function useIniciarCompra() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (viaje: ViajeEntrada) => unwrap(api.POST("/api/v1/compras", { body: viaje })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["mis-viajes"] });
    },
  });
}
