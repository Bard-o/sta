import { Glass } from "@/components/ui/glass";

/** S18 Pago con monedero (HU-25). `:compraId` y `?seleccion=<id>`. La pantalla se construye en #134. */
export function CompraPagoPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="sta-h1">Paga con tu monedero</h1>
      <Glass title="En construcción">
        <p className="body sta-muted">Esta pantalla llega en la iteración 2.</p>
      </Glass>
    </div>
  );
}
