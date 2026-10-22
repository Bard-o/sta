import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type ReactNode } from "react";
import { useForm, useFormContext, type FieldPath } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";
import { ApiError, type Schemas } from "@/api/client";
import { useRegistro } from "@/auth/registro";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import { ProfileImage } from "@/components/ui/profile-image";
import { Select } from "@/components/ui/select";
import { AYUDA_CONTRASENA, esquemaContrasena } from "@/lib/contrasena";

type TipoDocumento = Schemas["RegistroClienteEntrada"]["tipo_documento"];
type Genero = Schemas["RegistroClienteEntrada"]["genero"];

const TIPOS_DOCUMENTO: { value: TipoDocumento; label: string }[] = [
  { value: "CC", label: "Cédula de ciudadanía" },
  { value: "TI", label: "Tarjeta de identidad" },
  { value: "RC", label: "Registro civil" },
  { value: "CE", label: "Cédula de extranjería" },
  { value: "PA", label: "Pasaporte" },
];

const GENEROS: { value: Genero; label: string }[] = [
  { value: "femenino", label: "Femenino" },
  { value: "masculino", label: "Masculino" },
  { value: "otro", label: "Otro" },
];

/** Hoy como aaaa-mm-dd en la hora local de quien registra. */
const hoy = () => new Date().toLocaleDateString("sv-SE");

const requerido = (mensaje: string) => z.string().trim().min(1, mensaje);

const esquema = z.object({
  tipo_documento: z
    .string()
    .refine((v): v is TipoDocumento => TIPOS_DOCUMENTO.some((t) => t.value === v), {
      message: "Elige el tipo de documento.",
    }),
  numero_documento: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9]{3,20}$/, "Usa de 3 a 20 letras o números, sin espacios ni puntos."),
  genero: z.string().refine((v): v is Genero => GENEROS.some((g) => g.value === v), {
    message: "Elige tu género.",
  }),
  nombres: requerido("Escribe tus nombres."),
  apellidos: requerido("Escribe tus apellidos."),
  fecha_nacimiento: requerido("Escribe tu fecha de nacimiento.").refine((v) => v <= hoy(), {
    message: "La fecha de nacimiento no puede ser futura.",
  }),
  lugar_nacimiento: requerido("Escribe tu lugar de nacimiento."),
  direccion_facturacion: requerido("Escribe tu dirección de facturación."),
  email: z.string().trim().pipe(z.email("Escribe un correo válido, por ejemplo nombre@correo.co.")),
  nombre_usuario: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9._-]{3,50}$/, "Usa de 3 a 50 letras, números, punto, guion o guion bajo."),
  contrasena: esquemaContrasena,
  acepta_politica: z.boolean().refine((v) => v, {
    message: "Debes aceptar la política de tratamiento de datos personales para crear la cuenta.",
  }),
});

type Entrada = z.input<typeof esquema>;
type Datos = z.output<typeof esquema>;

const CAMPOS = Object.keys(esquema.shape) as FieldPath<Entrada>[];

function Texto({
  name,
  label,
  className,
  ayuda,
  ...props
}: {
  name: FieldPath<Entrada>;
  label: string;
  className?: string;
  ayuda?: ReactNode;
} & Omit<React.ComponentProps<typeof Input>, "name">) {
  const { control } = useFormContext<Entrada>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input {...props} {...field} value={String(field.value)} />
          </FormControl>
          {ayuda && <FormDescription>{ayuda}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function Lista({
  name,
  label,
  opciones,
  placeholder,
}: {
  name: FieldPath<Entrada>;
  label: string;
  opciones: { value: string; label: string }[];
  placeholder?: string;
}) {
  const { control } = useFormContext<Entrada>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="sta-field--select">
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Select {...field} value={String(field.value)}>
              {placeholder && (
                <option value="" disabled>
                  {placeholder}
                </option>
              )}
              {opciones.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** S01 · Registro de cliente (HU-01). Con sesión, la ruta SoloVisitantes redirige al inicio. */
export function RegistroPage() {
  const registro = useRegistro();
  const [imagen, setImagen] = useState<File | null>(null);
  const [errorImagen, setErrorImagen] = useState<string>();
  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: {
      tipo_documento: "CC",
      numero_documento: "",
      genero: "",
      nombres: "",
      apellidos: "",
      fecha_nacimiento: "",
      lugar_nacimiento: "",
      direccion_facturacion: "",
      email: "",
      nombre_usuario: "",
      contrasena: "",
      acepta_politica: false,
    },
  });

  const enviar = form.handleSubmit((datos) => {
    setErrorImagen(undefined);
    registro.mutate(
      { datos, imagen },
      {
        onError: (error) => {
          if (!(error instanceof ApiError)) return;
          // IU-07: cada error se muestra junto a su campo.
          for (const [campo, mensaje] of Object.entries(error.campos)) {
            if (campo === "imagen") setErrorImagen(mensaje);
            else if (CAMPOS.includes(campo as FieldPath<Entrada>)) {
              form.setError(campo as FieldPath<Entrada>, { message: mensaje });
            }
          }
        },
      },
    );
  });

  // Los errores con campo se pintan junto al campo; el resto va en un aviso general.
  const error = registro.error;
  const errorGeneral =
    error && !(error instanceof ApiError && Object.keys(error.campos).length > 0)
      ? error.message
      : null;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">Crea tu cuenta</h1>
        <p className="sta-sub">
          Con tu cuenta puedes reservar, comprar y hacer check-in. Te enviaremos un enlace para
          verificar tu correo.
        </p>
      </div>

      <Glass as="div">
        <Form {...form}>
          <form onSubmit={enviar} noValidate className="grid gap-6 lg:grid-cols-4">
            <ProfileImage
              className="order-first lg:order-last lg:col-span-1"
              onChange={(archivo) => {
                setImagen(archivo);
                setErrorImagen(undefined);
              }}
              error={errorImagen}
            />

            <div className="flex flex-col gap-4 lg:col-span-3">
              {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Lista name="tipo_documento" label="Tipo de documento" opciones={TIPOS_DOCUMENTO} />
                <Texto name="numero_documento" label="Número de documento" inputMode="text" />
                <Lista
                  name="genero"
                  label="Género"
                  opciones={GENEROS}
                  placeholder="Selecciona una opción"
                />
                <Texto name="nombres" label="Nombres" autoComplete="given-name" />
                <Texto name="apellidos" label="Apellidos" autoComplete="family-name" />
                <Texto
                  name="fecha_nacimiento"
                  label="Fecha de nacimiento"
                  type="date"
                  max={hoy()}
                  autoComplete="bday"
                />
                <Texto name="lugar_nacimiento" label="Lugar de nacimiento" />
                <Texto
                  name="direccion_facturacion"
                  label="Dirección de facturación"
                  className="sm:col-span-2"
                  autoComplete="street-address"
                />
                <Texto name="email" label="Correo electrónico" type="email" autoComplete="email" />
                <Texto name="nombre_usuario" label="Nombre de usuario" autoComplete="username" />
                <Texto
                  name="contrasena"
                  label="Contraseña"
                  type="password"
                  autoComplete="new-password"
                  ayuda={AYUDA_CONTRASENA}
                />
              </div>

              <FormField
                control={form.control}
                name="acepta_politica"
                render={({ field }) => (
                  <FormItem>
                    <div className="flex items-start gap-3">
                      <FormControl>
                        <Checkbox
                          name={field.name}
                          ref={field.ref}
                          checked={field.value}
                          onBlur={field.onBlur}
                          onChange={(e) => field.onChange(e.target.checked)}
                        />
                      </FormControl>
                      <FormLabel className="text-ink">
                        Acepto la política de tratamiento de datos personales (Ley 1581 de 2012).{" "}
                        <span className="sta-muted">Obligatorio.</span>
                      </FormLabel>
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex flex-wrap items-center gap-4">
                <Button type="submit" variant="primary" disabled={registro.isPending}>
                  {registro.isPending ? "Creando cuenta…" : "Crear cuenta"}
                </Button>
                <p className="label sta-muted">
                  ¿Ya tienes cuenta?{" "}
                  <Link className="sta-link" to="/login">
                    Inicia sesión
                  </Link>
                </p>
              </div>
            </div>
          </form>
        </Form>
      </Glass>
    </div>
  );
}
