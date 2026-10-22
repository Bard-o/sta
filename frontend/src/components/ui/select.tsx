import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

/** Lista desplegable nativa pintada como el campo del sistema de diseño (sta-input + chevron).
 *  Va dentro de `FormControl`, en un `FormItem` con la clase `sta-field--select`. */
export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <>
      <select className={cn("sta-input", className)} {...props}>
        {children}
      </select>
      <span className="sta-field__trail">
        <Icon name="chevron-down" />
      </span>
    </>
  );
}
