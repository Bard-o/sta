import { Glass } from "@/components/ui/glass";

/** S16 Carrito (HU-22, HU-23). La pantalla se construye en #127. */
export function CarritoPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="sta-h1">Tu carrito</h1>
      <Glass title="En construcción">
        <p className="body sta-muted">Esta pantalla llega en la iteración 2.</p>
      </Glass>
    </div>
  );
}
