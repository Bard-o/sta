import { useSearchParams } from "react-router";
import type { FiltrosMovimientos } from "@/auth/monedero";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { cop } from "@/lib/format";
import { useSaldo } from "./compra-pago/api";
import { Movimientos } from "./monedero/movimientos";
import { PanelTarjetas } from "./monedero/tarjetas";

const TIPOS = ["recarga", "compra", "reembolso"] as const;

/** S22 Monedero: saldo, tarjetas y movimientos (HU-29, HU-31). Los filtros de los movimientos
 *  viven en la dirección. Registrar tarjeta y recargar son S23 (#133). */
export function MonederoPage() {
  const [params, setParams] = useSearchParams();
  const tipo = params.get("tipo");
  const filtros: FiltrosMovimientos = {
    tipo: TIPOS.find((t) => t === tipo) ?? "",
    desde: params.get("desde") ?? "",
    hasta: params.get("hasta") ?? "",
    pagina: Math.max(1, Math.trunc(Number(params.get("pagina"))) || 1),
  };
  const saldo = useSaldo();

  function cambiar(cambios: Partial<Record<"tipo" | "desde" | "hasta" | "pagina", string>>) {
    setParams(
      (previos) => {
        const siguiente = new URLSearchParams(previos);
        for (const [clave, valor] of Object.entries(cambios)) {
          if (valor) siguiente.set(clave, valor);
          else siguiente.delete(clave);
        }
        return siguiente;
      },
      { replace: true },
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <h1 className="sta-h1">Monedero</h1>
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="flex w-full flex-col gap-6 lg:w-96 lg:shrink-0">
          <Glass aria-label="Saldo">
            <p className="overline sta-muted">SALDO DISPONIBLE</p>
            {saldo.isPending && <p className="body sta-muted">Cargando tu saldo…</p>}
            {saldo.isError && <Notice tone="danger">{saldo.error.message}</Notice>}
            {saldo.data && <p className="display-xl">{cop(saldo.data.saldo)}</p>}
            <div className="mt-4">
              <Button variant="primary" href="/monedero/recargar">
                Recargar
              </Button>
            </div>
          </Glass>
          <PanelTarjetas />
        </div>
        <Movimientos filtros={filtros} onCambiar={cambiar} />
      </div>
    </div>
  );
}
