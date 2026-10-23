import { useEffect, useRef, useState } from "react";
import { validarImagen } from "@/auth/imagen-perfil";
import { cn } from "@/lib/utils";
import { Button } from "./button";
import { Icon } from "./icon";

export interface ProfileImageProps {
  /** Recibe el archivo válido, o null cuando la persona lo quita. */
  onChange: (archivo: File | null) => void;
  /** Error que viene del servidor (campos.imagen). */
  error?: string;
  /** Imagen que ya tiene la cuenta, si la hay. */
  urlActual?: string | null;
  /** Mostrar la imagen elegida antes de enviarla (registro). En el perfil se sube al elegirla y
   *  solo se muestra la que guardó el servidor. */
  previsualizar?: boolean;
  /** Agrega «(opcional)» al título (en el registro; en el perfil ya no aplica). */
  opcional?: boolean;
  /** Hay una subida o un borrado en curso. */
  ocupado?: boolean;
  className?: string;
}

/** Imagen de perfil opcional (S01, S05): vista previa circular, «Subir imagen» y «Quitar». */
export function ProfileImage({
  onChange,
  error,
  urlActual,
  previsualizar = true,
  opcional = true,
  ocupado,
  className,
}: ProfileImageProps) {
  const entrada = useRef<HTMLInputElement>(null);
  const vistaActual = useRef<string | null>(null);
  const [vista, setVista] = useState<string | null>(null);
  const [errorLocal, setErrorLocal] = useState<string | null>(null);
  const [fallida, setFallida] = useState<string | null>(null);

  useEffect(
    () => () => {
      if (vistaActual.current) URL.revokeObjectURL(vistaActual.current);
    },
    [],
  );

  function poner(url: string | null) {
    if (vistaActual.current) URL.revokeObjectURL(vistaActual.current);
    vistaActual.current = url;
    setVista(url);
  }

  function alElegir(archivo: File | undefined) {
    if (!archivo) return;
    const problema = validarImagen(archivo);
    setErrorLocal(problema);
    if (problema) return;
    if (previsualizar) poner(URL.createObjectURL(archivo));
    onChange(archivo);
    // Permite elegir de nuevo el mismo archivo si la subida falla.
    if (!previsualizar && entrada.current) entrada.current.value = "";
  }

  function quitar() {
    poner(null);
    setErrorLocal(null);
    onChange(null);
    if (entrada.current) entrada.current.value = "";
  }

  const imagen = vista ?? (urlActual && urlActual !== fallida ? urlActual : null);
  const hayImagen = Boolean(vista ?? urlActual);
  const mensaje = errorLocal ?? error;

  return (
    <div className={cn("flex flex-col items-center gap-3 text-center", className)}>
      <div className="grid size-28 shrink-0 place-items-center overflow-hidden rounded-pill border border-control-line bg-glass-inset">
        {imagen ? (
          <img
            src={imagen}
            alt="Tu imagen de perfil"
            className="size-full object-cover"
            onError={() => setFallida(imagen)}
          />
        ) : (
          <span className="label sta-muted">Foto</span>
        )}
      </div>
      <div>
        <p className="label">Imagen de perfil{opcional ? " (opcional)" : ""}</p>
        <p className="caption sta-muted">JPG o PNG, máximo 2 MB</p>
      </div>
      <input
        ref={entrada}
        type="file"
        accept="image/jpeg,image/png"
        aria-label="Archivo de imagen de perfil"
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => alElegir(e.target.files?.[0])}
      />
      <div className="flex flex-wrap justify-center gap-2">
        <Button size="sm" onClick={() => entrada.current?.click()} disabled={ocupado}>
          {hayImagen ? "Cambiar imagen" : "Subir imagen"}
        </Button>
        {hayImagen && (
          <Button size="sm" variant="ghost" onClick={quitar} disabled={ocupado}>
            Quitar
          </Button>
        )}
      </div>
      {mensaje && (
        <p role="alert" className="sta-field__msg justify-center text-danger">
          <Icon name="alert" />
          {mensaje}
        </p>
      )}
    </div>
  );
}
