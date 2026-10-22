import { cn } from "@/lib/utils";
import { Button } from "./button";

export interface PagerProps {
  /** Página actual, desde 1. */
  pagina: number;
  total: number;
  porPagina: number;
  onChange: (pagina: number) => void;
  className?: string;
}

/** Números a mostrar: siempre la primera, la última y dos a cada lado de la actual. */
function numeros(actual: number, ultima: number): (number | "…")[] {
  const lista: (number | "…")[] = [];
  let previo = 0;
  for (let n = 1; n <= ultima; n++) {
    if (n === 1 || n === ultima || Math.abs(n - actual) <= 2) {
      if (n - previo > 1) lista.push("…");
      lista.push(n);
      previo = n;
    }
  }
  return lista;
}

/** Paginación de los listados (`sta-pager`): Anterior, números y Siguiente. La actual es una
 *  píldora `invert` con `aria-current`. */
export function Pager({ pagina, total, porPagina, onChange, className }: PagerProps) {
  const ultima = Math.max(1, Math.ceil(total / porPagina));
  if (ultima === 1) return null;
  return (
    <nav className={cn("sta-pager", className)} aria-label="Paginación">
      <Button size="sm" variant="ghost" disabled={pagina <= 1} onClick={() => onChange(pagina - 1)}>
        Anterior
      </Button>
      {numeros(pagina, ultima).map((n, i) =>
        n === "…" ? (
          <span key={`p${i}`} aria-hidden="true">
            …
          </span>
        ) : (
          <button
            key={n}
            type="button"
            className="sta-pager__n"
            aria-current={n === pagina ? "page" : undefined}
            aria-label={`Página ${n}`}
            onClick={() => onChange(n)}
          >
            {n}
          </button>
        ),
      )}
      <Button
        size="sm"
        variant="ghost"
        disabled={pagina >= ultima}
        onClick={() => onChange(pagina + 1)}
      >
        Siguiente
      </Button>
    </nav>
  );
}
