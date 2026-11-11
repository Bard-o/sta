import { useForm, type FieldPath } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";
import { ApiError, type Schemas } from "@/api/client";
import {
  useCompletarInvitacion,
  useValidarInvitacion,
} from "@/auth/invitacion-administrador";
import { INICIO_ROL } from "@/auth/roles";
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
import { esquemaContrasena } from "@/lib/contrasena";
import { fechaMinimaNacimiento, hoy, MENSAJE_EDAD_MAXIMA } from "@/lib/persona";

const MENSAJE_ENLACE_INVALIDO =
  "El enlace no es válido o venció. Pide al root una invitación nueva.";

const TIPOS_DOCUMENTO = [
  { value: "CC", label: "Cédula de ciudadanía" },
  { value: "TI", label: "Tarjeta de identidad" },
  { value: "RC", label: "Registro civil" },
  { value: "CE", label: "Cédula de extranjería" },
  { value: "PA", label: "Pasaporte" },
] as const;

const GENEROS = [
  { value: "femenino", label: "Femenino" },
  { value: "masculino", label: "Masculino" },
  { value: "otro", label: "Otro" },
] as const;

const esquema = z
  .object({
    tipo_documento: z.enum(["CC", "TI", "RC", "CE", "PA"]),
    numero_documento: z
      .string()
      .trim()
      .regex(
        /^[A-Za-z0-9]{3,20}$/,
        "Debe tener entre 3 y 20 letras o números, sin espacios ni puntos.",
      ),
    nombres: z
      .string()
      .trim()
      .min(1, "Escribe tus nombres.")
      .max(100)
      .regex(/^($|\p{L}[\p{L} '.-]*$)/u, "Usa solo letras, espacios, apóstrofo o guion."),
    apellidos: z
      .string()
      .trim()
      .min(1, "Escribe tus apellidos.")
      .max(100)
      .regex(/^($|\p{L}[\p{L} '.-]*$)/u, "Usa solo letras, espacios, apóstrofo o guion."),
    fecha_nacimiento: z
      .string()
      .min(1, "Elige tu fecha de nacimiento.")
      .refine((valor) => !valor || valor <= hoy(), "La fecha de nacimiento no puede ser futura.")
      .refine((valor) => !valor || valor >= fechaMinimaNacimiento(), MENSAJE_EDAD_MAXIMA),
    lugar_nacimiento: z.string().trim().min(1, "Escribe tu lugar de nacimiento.").max(120),
    direccion_facturacion: z
      .string()
      .trim()
      .min(1, "Escribe tu dirección de facturación.")
      .max(200),
    genero: z
      .union([z.literal(""), z.enum(["femenino", "masculino", "otro"])])
      .refine((valor) => valor !== "", "Elige tu género."),
    contrasena: esquemaContrasena,
    confirmacion: z.string().min(1, "Repite la contraseña."),
  })
  .refine((datos) => datos.contrasena === datos.confirmacion, {
    path: ["confirmacion"],
    message: "No coincide con la contraseña.",
  });

type Datos = z.input<typeof esquema>;

const CAMPOS: FieldPath<Datos>[] = [
  "tipo_documento",
  "numero_documento",
  "nombres",
  "apellidos",
  "fecha_nacimiento",
  "lugar_nacimiento",
  "direccion_facturacion",
  "genero",
  "contrasena",
  "confirmacion",
];

function EnlaceInvalido() {
  return (
    <Glass as="div" title="Enlace no válido">
      <p className="mb-4 flex items-start gap-2">
        <Icon name="alert" className="text-danger" />
        <span>{MENSAJE_ENLACE_INVALIDO}</span>
      </p>
      <Button variant="primary" href="/login">
        Ir a iniciar sesión
      </Button>
    </Glass>
  );
}

/** Pantalla pública del enlace de invitación (HU-10, HU-12). */
export function CompletarRegistroPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const validacion = useValidarInvitacion(token);
  const completar = useCompletarInvitacion();
  const navegar = useNavigate();
  const form = useForm<Datos>({
    defaultValues: {
      tipo_documento: "CC",
      numero_documento: "",
      nombres: "",
      apellidos: "",
      fecha_nacimiento: "",
      lugar_nacimiento: "",
      direccion_facturacion: "",
      genero: "",
      contrasena: "",
      confirmacion: "",
    },
  });

  const enviar = form.handleSubmit((datos) => {
    if (!token || !validacion.data) return;
    const resultado = esquema.safeParse(datos);
    if (!resultado.success) {
      for (const problema of resultado.error.issues) {
        const campo = problema.path[0];
        if (typeof campo === "string") {
          form.setError(campo as FieldPath<Datos>, { message: problema.message });
        }
      }
      return;
    }
    const cuerpo: Schemas["CompletarInvitacionEntrada"] = {
      ...resultado.data,
      token,
      // El wireframe no pide teléfono; el contrato lo deja opcional.
      telefono: null,
      genero: resultado.data.genero as Schemas["CompletarInvitacionEntrada"]["genero"],
    };
    completar.mutate(cuerpo, {
      onSuccess: () => navegar(INICIO_ROL.admin, { replace: true }),
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        // IU-07: el error de cada campo se muestra junto a ese campo.
        for (const [campo, mensaje] of Object.entries(error.campos)) {
          if (CAMPOS.includes(campo as FieldPath<Datos>)) {
            form.setError(campo as FieldPath<Datos>, { message: mensaje });
          }
        }
      },
    });
  });

  if (
    !token ||
    validacion.isError ||
    (completar.error instanceof ApiError && completar.error.codigo === "enlace_invalido")
  ) {
    return <EnlaceInvalido />;
  }

  if (validacion.isPending || !validacion.data) {
    return (
      <Glass as="div" title="Comprobando la invitación">
        <p className="body sta-muted">Estamos revisando tu enlace…</p>
      </Glass>
    );
  }

  const invitacion = validacion.data;
  const errorGeneral = (() => {
    const error = completar.error;
    if (!error) return null;
    if (!(error instanceof ApiError)) return error.message;
    if (error.codigo === "datos_invalidos" || Object.keys(error.campos).length > 0) return null;
    return error.message;
  })();

  return (
    <div className="flex flex-col gap-6">
      <Notice tone="info">
        Invitación para <strong>{invitacion.nombre_usuario}</strong>. El correo{" "}
        <strong>{invitacion.email}</strong> ya está verificado.
      </Notice>

      <div>
        <h1 className="sta-h1">Completa tu registro</h1>
        <p className="sta-sub">
          Estos son tus datos personales. Tu documento y tu correo no pueden repetirse entre
          administradores.
        </p>
      </div>

      <Glass as="div" title="Tus datos">
        <Form {...form}>
          <form onSubmit={enviar} noValidate className="flex flex-col gap-6">
            {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <div className="sta-field">
                <span className="sta-field__label">Nombre de usuario</span>
                <p className="body-strong">{invitacion.nombre_usuario}</p>
              </div>

              <div className="sta-field">
                <span className="sta-field__label">Correo</span>
                <p className="body">{invitacion.email}</p>
              </div>

              <FormField
                control={form.control}
                name="tipo_documento"
                render={({ field }) => (
                  <FormItem className="sta-field--select">
                    <FormLabel>Tipo de documento</FormLabel>
                    <FormControl>
                      <select className="sta-input" {...field}>
                        {TIPOS_DOCUMENTO.map((tipo) => (
                          <option key={tipo.value} value={tipo.value}>
                            {tipo.label}
                          </option>
                        ))}
                      </select>
                    </FormControl>
                    <span className="sta-field__trail" aria-hidden="true">
                      <Icon name="chevron-down" />
                    </span>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="numero_documento"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Número de documento</FormLabel>
                    <FormControl>
                      <Input autoComplete="off" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="genero"
                render={({ field }) => (
                  <FormItem className="sta-field--select">
                    <FormLabel>Género</FormLabel>
                    <FormControl>
                      <select className="sta-input" {...field}>
                        <option value="">Elige…</option>
                        {GENEROS.map((genero) => (
                          <option key={genero.value} value={genero.value}>
                            {genero.label}
                          </option>
                        ))}
                      </select>
                    </FormControl>
                    <span className="sta-field__trail" aria-hidden="true">
                      <Icon name="chevron-down" />
                    </span>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="nombres"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombres</FormLabel>
                    <FormControl>
                      <Input autoComplete="given-name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="apellidos"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Apellidos</FormLabel>
                    <FormControl>
                      <Input autoComplete="family-name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="fecha_nacimiento"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Fecha de nacimiento</FormLabel>
                    <FormControl>
                      <Input
                        type="date"
                        autoComplete="bday"
                        min={fechaMinimaNacimiento()}
                        max={hoy()}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>dd/mm/aaaa</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="lugar_nacimiento"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Lugar de nacimiento</FormLabel>
                    <FormControl>
                      <Input autoComplete="off" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="direccion_facturacion"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Dirección de facturación</FormLabel>
                    <FormControl>
                      <Input autoComplete="street-address" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div>
              <h2 className="sta-panel-title">Define tu contraseña</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                <FormField
                  control={form.control}
                  name="contrasena"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contraseña</FormLabel>
                      <FormControl>
                        <Input type="password" autoComplete="new-password" {...field} />
                      </FormControl>
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
              </div>
            </div>

            <div>
              <Button type="submit" variant="primary" disabled={completar.isPending}>
                {completar.isPending ? "Guardando…" : "Guardar y entrar"}
              </Button>
            </div>
          </form>
        </Form>
      </Glass>
    </div>
  );
}
