import { cn } from "@/lib/utils";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Nombre accesible del grupo («Estado de la reserva»). */
  label: string;
  className?: string;
}

/** Filtro de pocas opciones excluyentes en una píldora (DESIGN.md › Segmented); la activa se
 *  pinta `invert`. Máximo 5 opciones: con más, un select. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: SegmentedProps<T>) {
  return (
    <div role="group" aria-label={label} className={cn("sta-seg", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className="sta-seg__opt"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
