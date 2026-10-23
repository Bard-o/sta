import { usePerfil } from "@/auth/perfil";
import { useSesion } from "@/auth/sesion";
import { Notice } from "@/components/ui/notice";
import { CambiarContrasena } from "./perfil-comun/contrasena";
import { DatosPersonales } from "./perfil-comun/datos-personales";
import { DesactivarCuenta } from "./perfil-comun/desactivar";
import { ImagenDePerfil } from "./perfil-comun/imagen";
import { Suscripcion } from "./perfil-comun/suscripcion";

/** S05 · Perfil y cuenta. Pantalla compartida por varias historias: cada una aporta su sección
 *  (datos e imagen: HU-07; contraseña: HU-06; correos: HU-08; desactivar: HU-09). El root no tiene perfil: solo ve
 *  el cambio de contraseña. */
export function PerfilPage() {
  const { data: usuario } = useSesion();
  const esRoot = usuario?.rol === "root";
  const perfil = usePerfil(Boolean(usuario) && !esRoot);

  if (esRoot) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div>
          <h1 className="sta-h1">Mi cuenta</h1>
          <p className="sta-sub">El root no tiene perfil: aquí solo cambia su contraseña.</p>
        </div>
        <CambiarContrasena principal />
      </div>
    );
  }

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
            <CambiarContrasena />
          </div>
          <div className="flex flex-col gap-4">
            <ImagenDePerfil perfil={perfil.data} />
            {perfil.data.rol === "cliente" && <Suscripcion perfil={perfil.data} />}
            {perfil.data.rol === "cliente" && <DesactivarCuenta />}
          </div>
        </div>
      )}
    </div>
  );
}
