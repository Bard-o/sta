import { useState } from "react";
import { toast } from "sonner";
import { ApiError, type Schemas } from "@/api/client";
import { useQuitarImagen, useSubirImagen } from "@/auth/perfil";
import { Glass } from "@/components/ui/glass";
import { ProfileImage } from "@/components/ui/profile-image";

/** S05 · Imagen de perfil (HU-07): se sube o se quita al momento, sin esperar «Guardar cambios». */
export function ImagenDePerfil({ perfil }: { perfil: Schemas["PerfilSalida"] }) {
  const subir = useSubirImagen();
  const quitar = useQuitarImagen();
  const [error, setError] = useState<string>();

  const alCambiar = (archivo: File | null) => {
    setError(undefined);
    const alFallar = (e: Error) =>
      setError(e instanceof ApiError ? (e.campos.imagen ?? e.message) : e.message);
    if (archivo) {
      subir.mutate(archivo, {
        onSuccess: () => toast.success("Actualizamos tu imagen de perfil."),
        onError: alFallar,
      });
    } else {
      quitar.mutate(undefined, {
        onSuccess: () => toast.success("Quitamos tu imagen de perfil."),
        onError: alFallar,
      });
    }
  };

  return (
    <Glass as="div">
      <ProfileImage
        urlActual={perfil.imagen_url}
        previsualizar={false}
        opcional={false}
        ocupado={subir.isPending || quitar.isPending}
        onChange={alCambiar}
        error={error}
      />
    </Glass>
  );
}
