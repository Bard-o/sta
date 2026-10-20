import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

export interface NoticeProps {
  tone?: "danger" | "info";
  children: ReactNode;
  className?: string;
}

/** Caja de aviso (la de los diálogos de DESIGN.md), con ícono además del color. */
export function Notice({ tone = "info", children, className }: NoticeProps) {
  return (
    <div
      className={cn("sta-notice", `sta-notice--${tone}`, className)}
      role={tone === "danger" ? "alert" : "status"}
    >
      <Icon name={tone === "danger" ? "alert" : "info"} />
      <div>{children}</div>
    </div>
  );
}
