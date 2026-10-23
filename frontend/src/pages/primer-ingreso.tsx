import { useForm, type FieldPath } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";
import { ApiError, type Schemas } from "@/api/client";
import { INICIO_ROL } from "@/auth/roles";
import { useCompletarPrimerIngreso } from "@/auth/sesion";
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

const POLITICA = /^(?=.*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])(?=.*\d).{8,}$/;
const MENSAJE_POLITICA = "Debe tener al menos 8 caracteres, con letras y números.";

/** Hoy en la zona del navegador, como aaaa-mm-dd (el mismo formato del control de fecha). */
function hoy(): string {
  return new Date().toLocaleDateString("en-CA");
}

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
    nombres: z.string().trim().min(1, "Escribe tus nombres.").max(100),
    apellidos: z.string().trim().min(1, "Escribe tus apellidos.").max(100),
    fecha_nacimiento: z
      .string()
      .min(1, "Elige tu fecha de nacimiento.")
      .refine((valor) => !valor || valor <= hoy(), "La fecha de nacimiento no puede ser futura."),
    lugar_nacimiento: z.string().trim().min(1, "Escribe tu lugar de nacimiento.").max(120),
    direccion_facturacion: z
      .string()
      .trim()
      .min(1, "Escribe tu dirección de facturación.")
      .max(200),
    genero: z
      .union([z.literal(""), z.enum(["femenino", "masculino", "otro"])])
      .refine((valor) => valor !== "", "Elige tu género."),
    email: z
      .string()
      .trim()
      .regex(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, "Escribe un correo válido."),
    contrasena_temporal: z.string().min(1, "Escribe la contraseña temporal."),
    contrasena_nueva: z.string().regex(POLITICA, MENSAJE_POLITICA),
    confirmacion: z.string().min(1, "Repite la contraseña nueva."),
  })
  .refine((datos) => datos.contrasena_nueva === datos.confirmacion, {
    path: ["confirmacion"],
    message: "No coincide con la contraseña nueva.",
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
  "email",
  "contrasena_temporal",
  "contrasena_nueva",
  "confirmacion",
];

/** S07 · Primer ingreso del administrador (HU-12, RF-02 a RF-04). */
export function PrimerIngresoPage() {
  const completar = useCompletarPrimerIngreso();
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
      email: "",
      contrasena_temporal: "",
      contrasena_nueva: "",
      confirmacion: "",
    },
  });

  const enviar = form.handleSubmit((datos) => {
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
    const cuerpo: Schemas["RegistroAdministradorEntrada"] = {
      ...resultado.data,
      // El wireframe S07 no pide teléfono; el contrato lo deja opcional.
      telefono: null,
      genero: resultado.data.genero as Schemas["RegistroAdministradorEntrada"]["genero"],
    };
    completar.mutate(cuerpo, {
      onSuccess: () => navegar(INICIO_ROL.admin, { replace: true }),
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        // IU-07: el error de cada campo se muestra junto al campo.
        for (const [campo, mensaje] of Object.entries(error.campos)) {
          if (CAMPOS.includes(campo as FieldPath<Datos>)) {
            form.setError(campo as FieldPath<Datos>, { message: mensaje });
          }
        }
      },
    });
  });

  const errorGeneral = (() => {
    const error = completar.error;
    if (!error) return null;
    if (!(error instanceof ApiError)) return error.message;
    // Si el error trae campos, cada mensaje va junto a su campo (IU-07); no se repite arriba.
    if (error.codigo === "datos_invalidos" || Object.keys(error.campos).length > 0) return null;
    return error.message;
  })();

  return (
    <div className="flex flex-col gap-6">
      <Notice>Completa tu registro para continuar. El menú se habilita cuando termines.</Notice>

      <div>
        <h1 className="sta-h1">Tus datos de administrador</h1>
        <p className="sta-sub">
          Son los mismos datos del registro de clientes. Tu documento y tu correo no pueden
          repetirse entre administradores.
        </p>
      </div>

      <Glass as="div">
        <Form {...form}>
          <form onSubmit={enviar} noValidate className="flex flex-col gap-6">
            {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
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
                      <Input type="date" autoComplete="bday" {...field} />
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

              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Correo</FormLabel>
                    <FormControl>
                      <Input type="email" autoComplete="email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div>
              <h2 className="sta-panel-title">Cambia tu contraseña temporal</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                <FormField
                  control={form.control}
                  name="contrasena_temporal"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contraseña temporal</FormLabel>
                      <FormControl>
                        <Input type="password" autoComplete="current-password" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="contrasena_nueva"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contraseña nueva</FormLabel>
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
                      <FormLabel>Repite la nueva</FormLabel>
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
