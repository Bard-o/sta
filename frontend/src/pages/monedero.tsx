import { Glass } from "@/components/ui/glass";

/** S22 Monedero: saldo, tarjetas y movimientos (HU-29, HU-31). La pantalla se construye en #132. */
export function MonederoPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="sta-h1">Monedero</h1>
      <Glass title="En construcción">
        <p className="body sta-muted">Esta pantalla llega en la iteración 2.</p>
      </Glass>
    </div>
  );
}
