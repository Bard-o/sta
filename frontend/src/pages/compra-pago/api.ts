import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export type Compra = Schemas["Viaje"];

export const compraKey = (compraId: number) => ["compra", compraId] as const;
export const MONEDERO_KEY = ["monedero"] as const;

/** La compra del cliente en su estado efectivo: una pendiente con el bloqueo vencido llega
 *  `vencida` (HU-25). Un 404 no se reintenta: la compra no existe o es de otro cliente. */
export function useCompra(compraId: number) {
  return useQuery({
    queryKey: compraKey(compraId),
    enabled: Number.isInteger(compraId) && compraId > 0,
    retry: false,
    queryFn: () =>
      unwrap(api.GET("/api/v1/compras/{compra_id}", { params: { path: { compra_id: compraId } } })),
  });
}

/** Saldo actual del monedero (HU-31), para el «saldo después» y para lo que falte. */
export function useSaldo() {
  return useQuery({
    queryKey: MONEDERO_KEY,
    queryFn: () => unwrap(api.GET("/api/v1/monedero")),
  });
}

/** Confirma la compra: cobra el total del monedero en una sola transacción (HU-25, RF-39). Con
 *  saldo insuficiente no cobra nada y las sillas siguen bloqueadas hasta que venza el bloqueo. */
export function useConfirmarCompra(compraId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/compras/{compra_id}/confirmar", {
          params: { path: { compra_id: compraId } },
        }),
      ),
    onSuccess: (compra) => {
      queryClient.setQueryData(compraKey(compraId), compra);
    },
    // Pase lo que pase se vuelve a leer: el saldo cambió, o el estado de la compra.
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: MONEDERO_KEY });
      void queryClient.invalidateQueries({ queryKey: compraKey(compraId) });
      void queryClient.invalidateQueries({ queryKey: ["mis-viajes"] });
    },
  });
}

/** Suelta la compra: libera las sillas bloqueadas (una ya cancelada o vencida responde igual). */
export function useSoltarCompra(compraId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/v1/compras/{compra_id}", { params: { path: { compra_id: compraId } } }),
      ),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: compraKey(compraId) });
    },
  });
}

/** Segundos que faltan para `venceEn` (se actualiza cada segundo); `null` si no hay vencimiento. */
export function useSegundosRestantes(venceEn: string | null): number | null {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    if (!venceEn) return;
    const id = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(id);
  }, [venceEn]);
  if (!venceEn) return null;
  return Math.max(0, Math.ceil((Date.parse(venceEn) - ahora) / 1000));
}

/** «14:32»: minutos y segundos que faltan. */
export function reloj(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
