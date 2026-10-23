import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export interface SwitchProps extends Omit<ComponentProps<"button">, "onChange" | "role"> {
  checked: boolean;
  onCheckedChange: (activado: boolean) => void;
}

/** Interruptor (role="switch"): activado se pinta con el acento y la perilla se desplaza, así que
 *  el estado no depende solo del color. Se rotula con `aria-labelledby` o `aria-label`. */
export function Switch({ checked, onCheckedChange, className, disabled, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "group inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-pill border border-control-line bg-field p-1 transition-colors aria-checked:border-accent aria-checked:bg-accent disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        className,
      )}
      {...props}
    >
      <span
        aria-hidden="true"
        className="size-5 rounded-pill bg-ink-muted transition-transform group-aria-checked:translate-x-5 group-aria-checked:bg-on-accent"
      />
    </button>
  );
}
