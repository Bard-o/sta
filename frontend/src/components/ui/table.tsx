// Table de shadcn/ui con el estilo de tablero de salidas (sta-board).
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="sta-board-wrap">
      <table className={cn("sta-board", className)} {...props} />
    </div>
  );
}

export function TableHeader(props: ComponentProps<"thead">) {
  return <thead {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TableRow({
  className,
  highlighted,
  ...props
}: ComponentProps<"tr"> & { highlighted?: boolean }) {
  return <tr className={cn(highlighted && "is-hl", className)} {...props} />;
}

/** `align="right"` para cifras: alineadas a la derecha y con dígitos tabulares. */
export function TableHead({
  className,
  align,
  ...props
}: Omit<ComponentProps<"th">, "align"> & { align?: "left" | "right" }) {
  return <th scope="col" className={cn(align === "right" && "is-num", className)} {...props} />;
}

export function TableCell({
  className,
  align,
  ...props
}: Omit<ComponentProps<"td">, "align"> & { align?: "left" | "right" }) {
  return <td className={cn(align === "right" && "is-num", className)} {...props} />;
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("caption sta-muted", className)} {...props} />;
}
