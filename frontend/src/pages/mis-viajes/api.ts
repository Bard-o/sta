import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import { MONEDERO_KEY } from "../compra-pago/api";
import { rangoDelMes } from "./filtros";

export type Viaje = Schemas["Viaje"];
export type TipoViaje = "reserva" | "compra";
export type EstadoReserva = "vigente" | "pagada" | "vencida" | "cancelada";

export const POR_PAGINA = 20;
export const MIS_VIAJES_KEY = ["mis-viajes"] as const;

/** Las reservas o las compras del cliente (S19), de la más reciente a la más antigua. El mes
 *  filtra por el día de salida del primer tramo, en hora de Colombia. */
export function useMisViajes(p: {
  tipo: TipoViaje;
  estado: EstadoReserva | "";
  mes: string;
  pagina: number;
}) {
  const { desde, hasta } = rangoDelMes(p.mes);
  const query = {
    tipo: p.tipo,
    estado: p.estado || undefined,
    desde,
    hasta,
    pagina: p.pagina,
    por_pagina: POR_PAGINA,
  };
  return useQuery({
    queryKey: [...MIS_VIAJES_KEY, query],
    placeholderData: (anterior) => anterior,
    queryFn: () => unwrap(api.GET("/api/v1/mis-viajes", { params: { query } })),
  });
}

/** Paga una reserva vigente, completa o por viajero, al precio congelado (HU-27, RF-38). El
 *  código no cambia. Pase lo que pase se vuelve a leer la lista y el saldo: una reserva que dejó
 *  de estar vigente (`reserva_no_vigente`) o un saldo que cambió se reflejan al instante. */
export function usePagarReserva(reservaId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (viajeroIds: number[]) =>
      unwrap(
        api.POST("/api/v1/reservas/{reserva_id}/pagar", {
          params: { path: { reserva_id: reservaId } },
          body: { viajero_ids: viajeroIds },
        }),
      ),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: MIS_VIAJES_KEY });
      void queryClient.invalidateQueries({ queryKey: MONEDERO_KEY });
    },
  });
}
