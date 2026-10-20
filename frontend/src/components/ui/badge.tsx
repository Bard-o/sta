import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";
import type { IconName } from "./icon-paths";

export type Tone = "neutral" | "accent" | "success" | "danger" | "info";

export interface BadgeProps {
  tone?: Tone;
  icon?: IconName;
  children?: ReactNode;
  className?: string;
}

/** Estado en píldora: siempre con palabra, el color nunca va solo. */
export function Badge({ tone = "neutral", icon, children, className }: BadgeProps) {
  return (
    <span className={cn("sta-badge", tone !== "neutral" && `sta-badge--${tone}`, className)}>
      {icon && <Icon name={icon} />}
      {children}
    </span>
  );
}
