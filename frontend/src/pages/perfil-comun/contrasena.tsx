import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { useCambiarContrasena } from "@/auth/perfil";
import { Button } from "@/components/ui/button";
import { CampoTexto } from "@/components/ui/campos";
import { Form } from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { AYUDA_CONTRASENA, esquemaContrasena } from "@/lib/contrasena";

const esquema = z
  .object({
    contrasena_actual: z.string().min(1, "Escribe tu contraseña actual."),
    contrasena_nueva: esquemaContrasena,
    confirmacion: z.string().min(1, "Repite la contraseña nueva."),
  })
  .refine((d) => d.contrasena_nueva === d.confirmacion, {
    path: ["confirmacion"],
    message: "No coincide con la contraseña nueva.",
  });

type Datos = z.infer<typeof esquema>;
const VACIO: Datos = { contrasena_actual: "", contrasena_nueva: "", confirmacion: "" };

/** S05 · Contraseña (HU-06). La usan todos los roles; para el root es lo único de la pantalla.
 *  `principal` pinta el botón como la acción de la vista cuando no hay otra (root). */
export function CambiarContrasena({ principal = false }: { principal?: boolean }) {
  const cambio = useCambiarContrasena();
  const form = useForm<Datos>({ resolver: zodResolver(esquema), defaultValues: VACIO });

  const enviar = form.handleSubmit((datos) =>
    cambio.mutate(datos, {
      onSuccess: () => {
        form.reset(VACIO);
        toast.success("Cambiamos tu contraseña. La anterior ya no funciona.");
      },
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        for (const [campo, mensaje] of Object.entries(error.campos)) {
          if (campo in VACIO) form.setError(campo as keyof Datos, { message: mensaje });
        }
      },
    }),
  );

  const error = cambio.error;
  const errorGeneral =
    error && !(error instanceof ApiError && Object.keys(error.campos).length > 0)
      ? error.message
      : null;

  return (
    <Glass as="div" title="Contraseña">
      <Form {...form}>
        <form onSubmit={enviar} noValidate className="flex flex-col gap-4">
          {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}
          <div className="grid gap-3 sm:grid-cols-3">
            <CampoTexto<Datos>
              name="contrasena_actual"
              label="Actual"
              type="password"
              autoComplete="current-password"
            />
            <CampoTexto<Datos>
              name="contrasena_nueva"
              label="Nueva"
              type="password"
              autoComplete="new-password"
              ayuda={AYUDA_CONTRASENA}
            />
            <CampoTexto<Datos>
              name="confirmacion"
              label="Repite la nueva"
              type="password"
              autoComplete="new-password"
            />
          </div>
          <div>
            <Button
              type="submit"
              variant={principal ? "primary" : "secondary"}
              disabled={cambio.isPending}
            >
              {cambio.isPending ? "Cambiando…" : "Cambiar contraseña"}
            </Button>
          </div>
        </form>
      </Form>
    </Glass>
  );
}
