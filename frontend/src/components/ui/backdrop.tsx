import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface BackdropProps extends HTMLAttributes<HTMLDivElement> {
  /** URL de una foto real del terminal; se oscurece con `scrim`. */
  image?: string;
}

/** El fondo de la app. Va una sola vez, en la raíz; nunca lleva texto directo. */
export function Backdrop({ image, className, style, ...props }: BackdropProps) {
  return (
    <div
      {...props}
      className={cn("sta-backdrop", image && "sta-backdrop--photo", className)}
      style={
        image
          ? {
              ...style,
              backgroundImage: `linear-gradient(var(--scrim), var(--scrim)), url("${image}")`,
            }
          : style
      }
    />
  );
}
