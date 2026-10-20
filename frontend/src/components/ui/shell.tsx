import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { ChatFab } from "./chat-fab";

export interface ShellProps {
  nav?: ReactNode;
  children?: ReactNode;
  /** false oculta el botón Información (administrador y root no usan chatbot, Apéndice B). */
  chat?: boolean;
  onChat?: () => void;
  className?: string;
  style?: CSSProperties;
}

// Espacio bajo el contenido para que el botón Información (48 px) no tape lo último.
const ESPACIO_CHAT = { paddingBottom: "calc(var(--space-12) + 2 * var(--space-6))" };

/** La ventana de la app flotando sobre el Backdrop. Llena el alto disponible. */
export function Shell({ nav, children, chat = true, onChat, className, style }: ShellProps) {
  return (
    <div className={cn("sta-shell sta-glass flex-1", className)} style={style}>
      {nav}
      <main className="sta-shell__body" style={chat ? ESPACIO_CHAT : undefined}>
        {children}
      </main>
      {chat && <ChatFab onClick={onChat} />}
    </div>
  );
}
