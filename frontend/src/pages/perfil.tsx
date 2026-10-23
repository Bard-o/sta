import { usePerfil } from "@/auth/perfil";
import { Notice } from "@/components/ui/notice";
import { DatosPersonales } from "./perfil-comun/datos-personales";
import { ImagenDePerfil } from "./perfil-comun/imagen";

/** S05 · Perfil y cuenta. Pantalla compartida por varias historias: cada una aporta su sección
 *  (datos e imagen: HU-07). Solo cliente y administrador; el root no tiene perfil. */
export function PerfilPage() {
  const perfil = usePerfil();

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">Mi perfil</h1>
        <p className="sta-sub">
          El documento y el usuario identifican tu cuenta y no se pueden cambiar.
        </p>
      </div>

      {perfil.isError && <Notice tone="danger">{perfil.error.message}</Notice>}
      {perfil.data && (
        <div className="grid items-start gap-4 lg:grid-cols-3">
          <div className="flex flex-col gap-4 lg:col-span-2">
            <DatosPersonales perfil={perfil.data} />
          </div>
          <div className="flex flex-col gap-4">
            <ImagenDePerfil perfil={perfil.data} />
          </div>
        </div>
      )}
    </div>
  );
}
