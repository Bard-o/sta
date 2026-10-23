import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { toast } from "sonner";
import { z } from "zod";
import { ApiError, type Schemas } from "@/api/client";
import { useGuardarPerfil } from "@/auth/perfil";
import { Button } from "@/components/ui/button";
import { CampoLista, CampoTexto } from "@/components/ui/campos";
import { Form } from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { camposPersona, GENEROS, hoy, nombreTipoDocumento } from "@/lib/persona";

type Perfil = Schemas["PerfilSalida"];

const esquema = z.object({ ...camposPersona, telefono: z.string().trim() });
type Entrada = z.input<typeof esquema>;
type Datos = z.output<typeof esquema>;

const CAMPOS = Object.keys(esquema.shape) as (keyof Entrada)[];

/** Valores del formulario a partir del perfil. Si hay un correo pendiente, es el que se muestra:
 *  es el último que la persona escribió. */
const valoresDe = (p: Perfil): Entrada => ({
  nombres: p.nombres,
  apellidos: p.apellidos,
  telefono: p.telefono ?? "",
  genero: p.genero,
  fecha_nacimiento: p.fecha_nacimiento,
  lugar_nacimiento: p.lugar_nacimiento,
  direccion_facturacion: p.direccion_facturacion,
  email: p.email_pendiente ?? p.email,
});

function SoloLectura({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="sta-field__label">{etiqueta}</dt>
      <dd className="m-0 break-words text-ink">{valor}</dd>
    </div>
  );
}

function AyudaCorreo({ perfil }: { perfil: Perfil }) {
  if (perfil.email_pendiente) {
    return (
      <>
        Pendiente de verificar. Hasta entonces sigue vigente {perfil.email}.{" "}
        <Link className="sta-link" to="/verificar-correo">
          Reenviar enlace
        </Link>
      </>
    );
  }
  if (!perfil.email_verificado) {
    return (
      <>
        Tu correo aún no está verificado.{" "}
        <Link className="sta-link" to="/verificar-correo">
          Verificar correo
        </Link>
      </>
    );
  }
  return null;
}

/** S05 · Datos personales (HU-07). El documento y el usuario identifican la cuenta: solo lectura. */
export function DatosPersonales({ perfil }: { perfil: Perfil }) {
  const guardar = useGuardarPerfil();
  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: valoresDe(perfil),
  });

  const enviar = form.handleSubmit(({ telefono, ...datos }) =>
    guardar.mutate(
      { ...datos, telefono: telefono || null },
      {
        onSuccess: (nuevo) => {
          form.reset(valoresDe(nuevo));
          if (nuevo.email_pendiente && nuevo.email_pendiente !== perfil.email_pendiente) {
            toast.success(
              `Te enviamos un enlace de verificación a ${nuevo.email_pendiente}. Hasta que lo verifiques sigue vigente ${nuevo.email}.`,
            );
          } else {
            toast.success("Guardamos tus cambios.");
          }
        },
        onError: (error) => {
          if (!(error instanceof ApiError)) return;
          // IU-07: cada error se muestra junto a su campo.
          for (const [campo, mensaje] of Object.entries(error.campos)) {
            if (CAMPOS.includes(campo as keyof Entrada)) {
              form.setError(campo as keyof Entrada, { message: mensaje });
            }
          }
        },
      },
    ),
  );

  const error = guardar.error;
  const errorGeneral =
    error && !(error instanceof ApiError && Object.keys(error.campos).length > 0)
      ? error.message
      : null;

  return (
    <Glass as="div" title="Datos personales">
      <dl className="m-0 mb-4 grid gap-3 sm:grid-cols-3">
        <SoloLectura
          etiqueta="Tipo de documento"
          valor={nombreTipoDocumento(perfil.tipo_documento)}
        />
        <SoloLectura etiqueta="Número de documento" valor={perfil.numero_documento} />
        <SoloLectura etiqueta="Usuario" valor={perfil.nombre_usuario} />
      </dl>

      <Form {...form}>
        <form onSubmit={enviar} noValidate className="flex flex-col gap-4">
          {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <CampoTexto<Entrada> name="nombres" label="Nombres" autoComplete="given-name" />
            <CampoTexto<Entrada> name="apellidos" label="Apellidos" autoComplete="family-name" />
            <CampoTexto<Entrada>
              name="telefono"
              label="Teléfono (opcional)"
              type="tel"
              autoComplete="tel"
            />
            <CampoTexto<Entrada>
              name="fecha_nacimiento"
              label="Fecha de nacimiento"
              type="date"
              max={hoy()}
              autoComplete="bday"
            />
            <CampoTexto<Entrada> name="lugar_nacimiento" label="Lugar de nacimiento" />
            <CampoLista<Entrada> name="genero" label="Género" opciones={GENEROS} />
            <CampoTexto<Entrada>
              name="email"
              label="Correo"
              type="email"
              autoComplete="email"
              className="sm:col-span-2"
              ayuda={<AyudaCorreo perfil={perfil} />}
            />
            <CampoTexto<Entrada>
              name="direccion_facturacion"
              label="Dirección de facturación"
              className="sm:col-span-2 lg:col-span-3"
              autoComplete="street-address"
            />
          </div>
          <div>
            <Button type="submit" variant="primary" disabled={guardar.isPending}>
              {guardar.isPending ? "Guardando…" : "Guardar cambios"}
            </Button>
          </div>
        </form>
      </Form>
    </Glass>
  );
}
