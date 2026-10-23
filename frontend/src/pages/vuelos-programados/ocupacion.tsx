import type { Schemas } from "@/api/client";
import { Meter } from "@/components/ui/meter";

const CLASES = [
  ["primera", "Primera"],
  ["economica", "Económica"],
] as const;

/** Tiquetes vendidos por clase, con su barra: «Primera: 41 de 50 vendidas». Las reservas vigentes
 *  se mencionan aparte (todavía no son ventas). */
export function OcupacionPorClase({ ocupacion }: { ocupacion: Schemas["Ocupacion"] }) {
  return (
    <div className="flex flex-col gap-4">
      {CLASES.map(([clase, nombre]) => {
        const o = ocupacion[clase];
        const texto = `${nombre}: ${o.vendidas} de ${o.capacidad} vendidas`;
        return (
          <div key={clase} className="flex flex-col gap-1">
            <p className="body">
              {texto}
              {o.reservadas > 0 && ` (y ${o.reservadas} reservadas)`}
            </p>
            <Meter wide value={o.vendidas} max={o.capacidad} label={texto} />
          </div>
        );
      })}
    </div>
  );
}
