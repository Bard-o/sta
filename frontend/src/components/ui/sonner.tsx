// Toast: shadcn/ui usa sonner en lugar del antiguo componente toast. Sin estilos propios de
// sonner: vidrio fuerte del sistema de diseño (glass-strong, blur-lg, shadow-float).
import { Toaster as Sonner, type ToasterProps } from "sonner";

export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      position="bottom-center"
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "label flex w-full items-center gap-3 rounded-lg border border-glass-edge bg-glass-strong px-4 py-3 text-ink shadow-float backdrop-blur-lg",
          error: "text-danger",
          success: "text-success",
          description: "caption text-ink-muted",
        },
      }}
      {...props}
    />
  );
}
