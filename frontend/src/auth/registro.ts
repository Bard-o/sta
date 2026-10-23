import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, unwrap, type Schemas } from "@/api/client";
import { subirImagenPerfil } from "./imagen-perfil";
import { SESION_KEY, SESION_VENCIDA_KEY } from "./sesion";

/** Registro de cliente (HU-01). La imagen de perfil se sube después, con la sesión ya abierta:
 *  si falla, la cuenta queda creada y se avisa. Quien llama no necesita esperar la imagen para
 *  navegar: el aviso sale de aquí, aunque la pantalla ya se haya desmontado. */
export function useRegistro() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      datos,
      imagen,
    }: {
      datos: Schemas["RegistroClienteEntrada"];
      imagen: File | null;
    }) => {
      const usuario = await unwrap(api.POST("/api/v1/usuarios/registro", { body: datos }));
      let imagenSubida = true;
      if (imagen) {
        try {
          await subirImagenPerfil(imagen);
        } catch {
          imagenSubida = false;
        }
      }
      return { usuario, imagenSubida };
    },
    onSuccess: ({ usuario, imagenSubida }) => {
      queryClient.setQueryData(SESION_VENCIDA_KEY, false);
      queryClient.setQueryData(SESION_KEY, usuario);
      toast.success(`Creamos tu cuenta. Te enviamos un enlace para verificar ${usuario.email}.`);
      if (!imagenSubida) {
        toast.error("No pudimos subir tu imagen. Puedes intentarlo de nuevo desde tu perfil.");
      }
    },
  });
}
