import { cn } from "@/lib/utils";

export interface PasosProps {
  /** Nombres de los pasos, en orden: «Vuelos», «Viajeros», «Pago». */
  pasos: string[];
  /** Índice del paso en el que está el cliente; los anteriores quedan hechos. */
  actual: number;
  className?: string;
}

/** Indicador de pasos de la compra (S17 y S18): Vuelos → Viajeros → Pago. Hecho: punto de tinta;
 *  actual: punto amarillo con borde de tinta; pendiente: anillo. Cada paso lleva su nombre, el
 *  estado no va solo en el color. */
export function Pasos({ pasos, actual, className }: PasosProps) {
  return (
    <ol className={cn("flex items-center gap-3", className)} aria-label="Pasos de la compra">
      {pasos.map((nombre, i) => {
        const hecho = i < actual;
        const esActual = i === actual;
        return (
          <li
            key={nombre}
            className="flex items-center gap-3"
            aria-current={esActual ? "step" : undefined}
          >
            <span
              aria-hidden="true"
              className={cn(
                "size-3 rounded-full border-2",
                hecho && "border-invert bg-invert",
                esActual && "border-ink bg-accent",
                !hecho && !esActual && "border-control-line",
              )}
            />
            <span className={cn("title-md", !esActual && !hecho && "sta-muted")}>
              {nombre}
              {hecho && <span className="sr-only"> (hecho)</span>}
              {esActual && <span className="sr-only"> (paso actual)</span>}
            </span>
            {i < pasos.length - 1 && <span aria-hidden="true" className="h-px w-8 bg-line" />}
          </li>
        );
      })}
    </ol>
  );
}
