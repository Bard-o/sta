import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Casilla nativa (accesible por teclado y lector de pantalla) teñida con el color de acento. */
export function Checkbox({ className, ...props }: Omit<ComponentProps<"input">, "type">) {
  return (
    <input
      type="checkbox"
      className={cn(
        "size-5 shrink-0 cursor-pointer accent-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        className,
      )}
      {...props}
    />
  );
}
