import type { ElementType, HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface GlassProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  variant?: "base" | "strong" | "inset";
  padded?: boolean;
  as?: ElementType;
  title?: ReactNode;
  actions?: ReactNode;
}

/** Panel de vidrio. Dentro de `Shell` se pinta como tile (nunca vidrio sobre vidrio). */
export function Glass({
  variant = "base",
  padded = true,
  as: Tag = "section",
  title,
  actions,
  className,
  children,
  ...props
}: GlassProps) {
  return (
    <Tag
      {...props}
      className={cn(
        "sta-glass",
        variant === "strong" && "sta-glass--strong",
        variant === "inset" && "sta-glass--inset",
        padded && "sta-glass--pad",
        className,
      )}
    >
      {(title || actions) && (
        <div className="sta-panel-head">
          {title ? <h2 className="sta-panel-title">{title}</h2> : <span />}
          {actions}
        </div>
      )}
      {children}
    </Tag>
  );
}
