// Dialog de shadcn/ui (Radix: foco atrapado, Escape, aria) pintado con sta-scrim y sta-dialog.
// Toda acción irreversible pide confirmación con este Dialog (IU-07): título como pregunta,
// la acción destructiva en `danger` primero y «Volver» como `secondary`.
import type { ComponentProps, ReactNode } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";
import { Notice } from "./notice";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  className,
  children,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      {/* fixed: el velo cubre la ventana aunque la página tenga scroll. */}
      <DialogPrimitive.Overlay className="sta-scrim" style={{ position: "fixed" }}>
        <DialogPrimitive.Content className={cn("sta-dialog", className)} {...props}>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Overlay>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader(props: ComponentProps<"div">) {
  return <div {...props} />;
}

export function DialogTitle({ className, ...props }: ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title className={cn("sta-dialog__title", className)} {...props} />;
}

export function DialogDescription({
  className,
  ...props
}: ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogPrimitive.Description className={cn("sta-dialog__sub", className)} {...props} />;
}

/** Qué pasa después de confirmar («Se anularán, sus sillas se liberarán…»). */
export function DialogNotice({
  tone = "danger",
  children,
}: {
  tone?: "danger" | "info";
  children: ReactNode;
}) {
  return <Notice tone={tone}>{children}</Notice>;
}

export function DialogBody({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("sta-dialog__body", className)} {...props} />;
}

export function DialogFooter({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("sta-dialog__actions", className)} {...props} />;
}
