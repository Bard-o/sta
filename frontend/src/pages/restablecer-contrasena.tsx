import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router";
import { z } from "zod";
import { ApiError } from "@/api/client";
import {
  RUTA_RESTABLECER,
  useConfirmarRestablecimiento,
  useSolicitarRestablecimiento,
} from "@/auth/restablecimiento";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import { AYUDA_CONTRASENA, esquemaContrasena } from "@/lib/contrasena";

/** S04 · Restablecer contraseña (HU-05). Sin `?token=` pide el enlace; con él, define la nueva. */
export function RestablecerContrasenaPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6">
      <div>
        <h1 className="sta-h1">Restablece tu contraseña</h1>
        <p className="sta-sub">
          Por seguridad no guardamos tu contraseña: te enviamos un enlace para crear una nueva.
        </p>
      </div>
      {token ? <NuevaContrasena token={token} /> : <SolicitarEnlace />}
    </div>
  );
}

const esquemaCorreo = z.object({
  email: z.string().trim().pipe(z.email("Escribe un correo válido, por ejemplo nombre@correo.co.")),
});

function SolicitarEnlace() {
  const solicitud = useSolicitarRestablecimiento();
  const form = useForm<z.input<typeof esquemaCorreo>, unknown, z.output<typeof esquemaCorreo>>({
    resolver: zodResolver(esquemaCorreo),
    defaultValues: { email: "" },
  });

  const enviar = form.handleSubmit(({ email }) =>
    solicitud.mutate(email, {
      onError: (error) => {
        if (error instanceof ApiError && error.campos.email) {
          form.setError("email", { message: error.campos.email });
        }
      },
    }),
  );

  const error = solicitud.error;
  const errorGeneral =
    error && !(error instanceof ApiError && error.campos.email) ? error.message : null;

  return (
    <Glass as="div" title="Paso 1. Tu correo">
      <Form {...form}>
        <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
          {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Correo de la cuenta</FormLabel>
                <FormControl>
                  <Input type="email" autoComplete="email" autoFocus {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {solicitud.data && <Notice tone="info">{solicitud.data.mensaje}</Notice>}
          <div className="mt-1 flex flex-wrap items-center gap-4">
            <Button type="submit" variant="primary" disabled={solicitud.isPending}>
              {solicitud.isPending ? "Enviando…" : "Enviar enlace"}
            </Button>
            <Link className="sta-link" to="/login">
              Volver a iniciar sesión
            </Link>
          </div>
        </form>
      </Form>
    </Glass>
  );
}

const esquemaNueva = z
  .object({
    contrasena_nueva: esquemaContrasena,
    confirmacion: z.string().min(1, "Repite la contraseña nueva."),
  })
  .refine((d) => d.contrasena_nueva === d.confirmacion, {
    path: ["confirmacion"],
    message: "No coincide con la contraseña nueva.",
  });

type DatosNueva = z.infer<typeof esquemaNueva>;

function NuevaContrasena({ token }: { token: string }) {
  const confirmacion = useConfirmarRestablecimiento();
  const form = useForm<DatosNueva>({
    resolver: zodResolver(esquemaNueva),
    defaultValues: { contrasena_nueva: "", confirmacion: "" },
  });

  const enviar = form.handleSubmit((datos) =>
    confirmacion.mutate(
      { token, ...datos },
      {
        onError: (error) => {
          if (!(error instanceof ApiError)) return;
          for (const [campo, mensaje] of Object.entries(error.campos)) {
            if (campo === "contrasena_nueva" || campo === "confirmacion") {
              form.setError(campo, { message: mensaje });
            }
          }
        },
      },
    ),
  );

  if (confirmacion.isSuccess) {
    return (
      <Glass as="div" title="Contraseña actualizada">
        <p className="mb-4 flex items-start gap-2">
          <Icon name="check-circle" className="text-success" />
          <span>Listo. Cerramos tus sesiones abiertas: inicia sesión con tu contraseña nueva.</span>
        </p>
        <Button variant="primary" href="/login">
          Iniciar sesión
        </Button>
      </Glass>
    );
  }

  const error = confirmacion.error;
  if (error instanceof ApiError && error.codigo === "enlace_invalido") {
    return (
      <Glass as="div" title="Enlace vencido o ya usado">
        <Notice tone="danger">
          Este enlace venció o ya fue usado. Pide uno nuevo para restablecer tu contraseña.
        </Notice>
        <Button variant="primary" href={RUTA_RESTABLECER}>
          Pedir un enlace nuevo
        </Button>
      </Glass>
    );
  }
  const errorGeneral =
    error && !(error instanceof ApiError && Object.keys(error.campos).length > 0)
      ? error.message
      : null;

  return (
    <Glass as="div" title="Paso 2. Desde el enlace">
      <Form {...form}>
        <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
          {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}
          <FormField
            control={form.control}
            name="contrasena_nueva"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Contraseña nueva</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="new-password" autoFocus {...field} />
                </FormControl>
                <FormDescription>{AYUDA_CONTRASENA}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="confirmacion"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Repite la contraseña</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="new-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="mt-1">
            <Button type="submit" variant="primary" disabled={confirmacion.isPending}>
              {confirmacion.isPending ? "Guardando…" : "Guardar contraseña"}
            </Button>
          </div>
          <p className="caption sta-muted">
            Al guardar, cerramos las sesiones abiertas en tus otros dispositivos.
          </p>
        </form>
      </Form>
    </Glass>
  );
}
