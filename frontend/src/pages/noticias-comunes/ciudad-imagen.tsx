import { useState } from "react";
import { cn } from "@/lib/utils";

/** Imagen de la ciudad (banco de imágenes, SUP-30). Si no carga, se muestra el código de la
 *  ciudad en su lugar, para que nunca quede un ícono de imagen rota. */
export function CiudadImagen({
  src,
  codigo,
  nombre,
  className,
}: {
  src: string;
  codigo: string;
  nombre: string;
  className?: string;
}) {
  const [fallo, setFallo] = useState(false);
  if (fallo || !src) {
    return (
      <div
        className={cn(
          "bg-glass-inset text-ink-muted flex items-center justify-center rounded-md",
          "title-md",
          className,
        )}
        role="img"
        aria-label={`Imagen de ${nombre}`}
      >
        {codigo}
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={`Imagen de ${nombre}`}
      className={cn("rounded-md object-cover", className)}
      onError={() => setFallo(true)}
    />
  );
}
