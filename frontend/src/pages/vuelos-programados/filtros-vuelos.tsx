import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import type { Filtros } from "./filtros";

/** Texto + «desde» + «hasta» + «Limpiar filtros». Cada pantalla pone sus propias etiquetas. */
export function FiltrosVuelos({
  filtros,
  etiquetas,
  placeholder,
  nombre,
}: {
  filtros: Filtros;
  etiquetas: { q: string; desde: string; hasta: string };
  placeholder: string;
  nombre: string;
}) {
  const { texto, desde, hasta, periodoInvalido, hayFiltros, escribir, cambiar, limpiar } = filtros;
  return (
    <>
      <form
        role="search"
        aria-label={nombre}
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(e) => e.preventDefault()}
      >
        <Field
          label={etiquetas.q}
          className="lg:col-span-2"
          icon="search"
          value={texto}
          onChange={(e) => escribir(e.target.value)}
          placeholder={placeholder}
        />
        <Field
          label={etiquetas.desde}
          type="date"
          value={desde}
          onChange={(e) => cambiar({ desde: e.target.value, pagina: "" })}
        />
        <Field
          label={etiquetas.hasta}
          type="date"
          value={hasta}
          min={desde || undefined}
          error={periodoInvalido ? "La fecha final no puede ser anterior a la inicial." : undefined}
          onChange={(e) => cambiar({ hasta: e.target.value, pagina: "" })}
        />
      </form>
      {hayFiltros && (
        <div>
          <Button variant="ghost" size="sm" onClick={limpiar}>
            Limpiar filtros
          </Button>
        </div>
      )}
    </>
  );
}
