import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { useLogin, useSesionVencida } from "@/auth/sesion";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";

const esquema = z.object({
  usuario: z.string().trim().min(1, "Escribe tu nombre de usuario o tu correo."),
  contrasena: z.string().min(1, "Escribe tu contraseña."),
});

type Datos = z.infer<typeof esquema>;

/** S03 · Inicio de sesión (HU-03). La redirección tras entrar la hace la ruta SoloVisitantes. */
export function LoginPage() {
  const login = useLogin();
  const sesionVencida = useSesionVencida();
  const form = useForm<Datos>({
    resolver: zodResolver(esquema),
    defaultValues: { usuario: "", contrasena: "" },
  });

  const enviar = form.handleSubmit((datos) =>
    login.mutate(datos, {
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        // IU-07: los errores de un campo se muestran junto a ese campo.
        for (const [campo, mensaje] of Object.entries(error.campos)) {
          if (campo === "usuario" || campo === "contrasena")
            form.setError(campo, { message: mensaje });
        }
      },
    }),
  );

  const errorGeneral =
    login.error && !(login.error instanceof ApiError && login.error.codigo === "datos_invalidos")
      ? login.error.message
      : null;

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6">
      <div>
        <h1 className="sta-h1">Inicia sesión</h1>
        <p className="sta-sub">Clientes, administradores y root entran por aquí.</p>
      </div>

      <Glass as="div">
        <Form {...form}>
          <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
            {sesionVencida && !errorGeneral && (
              <Notice tone="info">Tu sesión venció por inactividad. Inicia sesión de nuevo.</Notice>
            )}
            {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

            <FormField
              control={form.control}
              name="usuario"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Usuario o correo</FormLabel>
                  <FormControl>
                    <Input autoComplete="username" autoFocus {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="contrasena"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Contraseña</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="current-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="mt-2 flex flex-wrap items-center gap-4">
              <Button type="submit" variant="primary" disabled={login.isPending}>
                {login.isPending ? "Entrando…" : "Iniciar sesión"}
              </Button>
              <Link className="sta-link" to="/restablecer-contrasena">
                Olvidé mi contraseña
              </Link>
            </div>
          </form>
        </Form>
      </Glass>

      <p className="label sta-muted">
        ¿No tienes cuenta?{" "}
        <Link className="sta-link" to="/registro">
          Crea una
        </Link>
      </p>
    </div>
  );
}
