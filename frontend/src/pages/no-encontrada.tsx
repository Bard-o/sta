import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";

export function NoEncontradaPage() {
  return (
    <Glass title="Página no encontrada">
      <p className="body sta-muted">La dirección no existe o todavía no está disponible.</p>
      <div className="mt-4">
        <Button href="/">Ir al inicio</Button>
      </div>
    </Glass>
  );
}
