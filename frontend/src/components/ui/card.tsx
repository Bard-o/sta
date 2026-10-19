// Card de shadcn/ui sobre el vidrio del sistema de diseño: es un `Glass` con sus partes.
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("sta-glass sta-glass--pad", className)} {...props} />;
}

export function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("sta-panel-head", className)} {...props} />;
}

export function CardTitle({ className, ...props }: ComponentProps<"h2">) {
  return <h2 className={cn("sta-panel-title", className)} {...props} />;
}

export function CardDescription({ className, ...props }: ComponentProps<"p">) {
  return <p className={cn("sta-sub", className)} {...props} />;
}

export function CardContent(props: ComponentProps<"div">) {
  return <div {...props} />;
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("sta-row mt-4", className)} {...props} />;
}
