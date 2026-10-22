import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm, useWatch, type FieldPath } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { CampoDinero, CampoLista, CampoTexto } from "@/components/ui/campos";
import { Form } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { desfase } from "@/lib/format";
import { hoy } from "@/lib/persona";
import { useDebounced } from "@/lib/use-debounced";
import { useCiudades, usePublicarVuelo, type VueloEntrada } from "./programar-vuelo/api";
import { VistaPrevia } from "./programar-vuelo/vista-previa";

const entero = (min: number, max: number, mensaje: string) =>
  z
    .string()
    .trim()
    .transform((s) => (s === "" ? "0" : s))
    .pipe(z.string().regex(/^\d+$/, mensaje))
    .transform(Number)
    .pipe(z.number().min(min, mensaje).max(max, mensaje));

const precio = (mensaje: string) =>
  z
    .string()
    .transform((s) => s.replace(/\D/g, ""))
    .pipe(z.string().min(1, mensaje))
    .transform(Number)
    .pipe(z.number().min(1, "El precio debe ser mayor que 0."));

const esquema = z
  .object({
    origen: z.string().min(1, "Elige la ciudad de origen."),
    destino: z.string().min(1, "Elige la ciudad de destino."),
    fecha_salida: z
      .string()
      .min(1, "Escribe la fecha de salida.")
      .refine((v) => v >= hoy(), { message: "La fecha de salida no puede ser pasada." }),
    hora_salida: z.string().regex(/^\d{2}:\d{2}$/, "Escribe la hora de salida, por ejemplo 06:00."),
    horas: entero(0, 23, "Las horas van de 0 a 23."),
    minutos: entero(0, 59, "Los minutos van de 0 a 59."),
    precio_economica: precio("Escribe el precio de económica, en pesos."),
    precio_primera: precio("Escribe el precio de primera, en pesos."),
  })
  .superRefine((d, ctx) => {
    if (d.origen && d.origen === d.destino) {
      ctx.addIssue({
        code: "custom",
        path: ["destino"],
        message: "El destino debe ser distinto del origen.",
      });
    }
    const total = d.horas * 60 + d.minutos;
    if (total < 1 || total > 1439) {
      ctx.addIssue({
        code: "custom",
        path: ["horas"],
        message: "La duración debe ser de más de 0 minutos y menos de 24 horas.",
      });
    }
  });

type Entrada = z.input<typeof esquema>;
type Datos = z.output<typeof esquema>;

const VACIO: Entrada = {
  origen: "",
  destino: "",
  fecha_salida: "",
  hora_salida: "",
  horas: "",
  minutos: "0",
  precio_economica: "",
  precio_primera: "",
};

const CAMPOS_API: Record<string, FieldPath<Entrada>> = {
  origen: "origen",
  destino: "destino",
  fecha_salida: "fecha_salida",
  hora_salida: "hora_salida",
  duracion_minutos: "horas",
  precio_economica: "precio_economica",
  precio_primera: "precio_primera",
};

const aEntradaApi = (d: Datos): VueloEntrada => ({
  origen: d.origen,
  destino: d.destino,
  fecha_salida: d.fecha_salida,
  hora_salida: d.hora_salida,
  duracion_minutos: d.horas * 60 + d.minutos,
  precio_economica: d.precio_economica,
  precio_primera: d.precio_primera,
});

/** S08 · Programar vuelo (HU-13). La vista previa se pide sola cuando el formulario es válido. */
export function ProgramarVueloPage() {
  const ciudades = useCiudades();
  const publicar = usePublicarVuelo();
  const [publicado, setPublicado] = useState<string>();
  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: VACIO,
  });

  const valores = useWatch({ control: form.control }) as Entrada;
  const parseado = esquema.safeParse(valores);
  const entradaVista = parseado.success ? aEntradaApi(parseado.data) : null;
  // Una petición cuando la persona deja de escribir, no una por tecla.
  const claveVista = useDebounced(entradaVista ? JSON.stringify(entradaVista) : null);
  const entradaDebounced = useMemo(
    () => (claveVista ? (JSON.parse(claveVista) as VueloEntrada) : null),
    [claveVista],
  );

  const opciones = useMemo(
    () =>
      [...(ciudades.data ?? [])]
        .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"))
        .map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.codigo})` })),
    [ciudades.data],
  );
  const origen = ciudades.data?.find((c) => c.codigo === valores.origen);
  const etiquetaHora = origen
    ? `Hora de salida (hora de ${origen.nombre}, ${desfase(
        /^\d{4}-\d{2}-\d{2}$/.test(valores.fecha_salida)
          ? new Date(`${valores.fecha_salida}T12:00:00Z`)
          : new Date(),
        origen.zona_horaria,
      )})`
    : "Hora de salida (hora local del origen)";

  const enviar = form.handleSubmit((datos) => {
    setPublicado(undefined);
    publicar.mutate(aEntradaApi(datos), {
      onSuccess: (vuelo) => {
        form.reset(VACIO);
        setPublicado(
          `Publicamos el vuelo ${vuelo.codigo} (${vuelo.origen.nombre} → ${vuelo.destino.nombre}). Ya tiene su noticia y su imagen en el carrusel.`,
        );
        toast.success(`Publicamos el vuelo ${vuelo.codigo}.`);
      },
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        // IU-07: cada error se muestra junto a su campo.
        for (const [campo, mensaje] of Object.entries(error.campos)) {
          const destino = CAMPOS_API[campo];
          if (destino) form.setError(destino, { message: mensaje });
        }
      },
    });
  });

  const error = publicar.error;
  const errorGeneral =
    error && !(error instanceof ApiError && Object.keys(error.campos).length > 0)
      ? error.message
      : null;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">Programar vuelo</h1>
        <p className="sta-sub">
          El código se asigna al guardar. Al publicarlo se crea la noticia y su imagen en el
          carrusel.
        </p>
      </div>

      <div className="grid items-start gap-8 lg:grid-cols-2">
        <Form {...form}>
          <form onSubmit={enviar} noValidate className="flex flex-col gap-4">
            {publicado && <Notice tone="info">{publicado}</Notice>}
            {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}
            {ciudades.isError && <Notice tone="danger">{ciudades.error.message}</Notice>}

            <div className="grid gap-3 sm:grid-cols-2">
              <CampoLista<Entrada>
                name="origen"
                label="Origen"
                opciones={opciones}
                placeholder="Selecciona una ciudad"
              />
              <CampoLista<Entrada>
                name="destino"
                label="Destino"
                opciones={opciones}
                placeholder="Selecciona una ciudad"
              />
              <CampoTexto<Entrada>
                name="fecha_salida"
                label="Fecha de salida"
                type="date"
                min={hoy()}
              />
              <CampoTexto<Entrada> name="hora_salida" label={etiquetaHora} type="time" />
              <fieldset className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0 sm:col-span-2">
                <legend className="sta-field__label mb-1">Duración</legend>
                <div className="grid grid-cols-2 gap-3">
                  <CampoTexto<Entrada> name="horas" label="Horas" inputMode="numeric" />
                  <CampoTexto<Entrada> name="minutos" label="Minutos" inputMode="numeric" />
                </div>
              </fieldset>
              <CampoDinero<Entrada> name="precio_economica" label="Precio por persona, económica" />
              <CampoDinero<Entrada> name="precio_primera" label="Precio por persona, primera" />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" variant="primary" disabled={publicar.isPending}>
                {publicar.isPending ? "Publicando…" : "Publicar vuelo"}
              </Button>
              <Button variant="secondary" href="/admin">
                Cancelar
              </Button>
            </div>
          </form>
        </Form>

        <VistaPrevia
          entrada={entradaDebounced}
          precio={parseado.success ? parseado.data.precio_economica : 0}
        />
      </div>
    </div>
  );
}
