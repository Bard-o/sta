import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Control de texto de 40 px con fondo `field` y borde `control-line`. */
export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return <input type={type} className={cn("sta-input", className)} {...props} />;
}
