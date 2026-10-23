import { cn } from "@/lib/utils";

export interface MeterProps {
  value: number;
  max: number;
  /** Texto que acompaña a la barra; por defecto «value / max». */
  label?: string;
  /** Barra a todo el ancho (resúmenes de ocupación), en lugar de la compacta de las tablas. */
  wide?: boolean;
  className?: string;
}

/** Medidor de ocupación (`sta-meter`): barra + cifra, así que el valor no depende del color. */
export function Meter({ value, max, label, wide, className }: MeterProps) {
  const porcentaje = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <span className={cn("sta-meter", wide && "flex-col items-stretch", className)}>
      <span
        role="meter"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-label={label ?? `${value} de ${max}`}
        className="sta-meter__track"
        style={wide ? { width: "100%" } : undefined}
      >
        <span className="sta-meter__fill" style={{ width: `${porcentaje}%` }} />
      </span>
      {!wide && (
        <span>
          {value} <span className="sta-meter__of">/ {max}</span>
        </span>
      )}
    </span>
  );
}
