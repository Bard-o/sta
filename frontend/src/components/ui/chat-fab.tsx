import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

export interface ChatFabProps {
  onClick?: () => void;
  label?: string;
  static?: boolean;
  className?: string;
  style?: CSSProperties;
}

/** Botón «Información» que abre el chatbot (IU-03). Solo visitante y cliente. */
export function ChatFab({
  onClick,
  label = "Información",
  static: enFlujo,
  className,
  style,
}: ChatFabProps) {
  return (
    <button
      type="button"
      className={cn("sta-chatfab", enFlujo && "sta-chatfab--static", className)}
      style={style}
      onClick={onClick}
    >
      <span className="sta-chatfab__dot">
        <Icon name="info" />
      </span>
      {label}
    </button>
  );
}
