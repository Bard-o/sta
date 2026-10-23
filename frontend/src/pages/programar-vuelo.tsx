import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CampoFichas, CampoTexto } from "@/components/ui/campos";
import { Form } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { Switch } from "@/components/ui/switch";
import { hoy } from "@/lib/persona";
import { useDebounced } from "@/lib/use-debounced";
import {
  usePublicarSerie,
  usePublicarVuelo,
  type SerieEntrada,
  type SerieSalida,
  type VueloEntrada,
} from "./programar-vuelo/api";
import {
  CAMPOS_API,
  DIAS,
  VACIO,
  aEntradaApi,
  aSerieApi,
  esquema,
  maximoHasta,
  type Datos,
  type Entrada,
} from "./programar-vuelo/esquema";
import { CamposVuelo } from "./programar-vuelo/campos-vuelo";
import { ResumenSerie } from "./programar-vuelo/resumen-serie";
import { VistaPrevia } from "./programar-vuelo/vista-previa";

type Vista = { vuelo: VueloEntrada } | { serie: SerieEntrada } | null;

/** S08 · Programar vuelo (HU-13) y programar vuelos recurrentes (HU-14). La vista previa se pide
 *  sola cuando el formulario es válido. */
export function ProgramarVueloPage() {
  const publicar = usePublicarVuelo();
  const publicarSerie = usePublicarSerie();
  const [publicado, setPublicado] = useState<string>();
  const [resumen, setResumen] = useState<{ serie: SerieSalida; dias: string[] }>();
  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: VACIO,
  });

  const valores = useWatch({ control: form.control }) as Entrada;
  const repite = valores.repite;
  const parseado = esquema.safeParse(valores);
  const vista: Vista = parseado.success
    ? repite
      ? { serie: aSerieApi(parseado.data) }
      : { vuelo: aEntradaApi(parseado.data) }
    : null;
  // Una petición cuando la persona deja de escribir, no una por tecla.
  const claveVista = useDebounced(vista ? JSON.stringify(vista) : null);
  const vistaEspera = useMemo(
    () => (claveVista ? (JSON.parse(claveVista) as NonNullable<Vista>) : null),
    [claveVista],
  );

  function alCambiarRepite(activado: boolean) {
    form.setValue("repite", activado);
    // «Desde» arranca en la fecha que ya se había escrito, o en hoy.
    if (activado && !form.getValues("desde")) {
      form.setValue("desde", form.getValues("fecha_salida") || hoy());
    }
    form.clearErrors();
  }

  // IU-07: cada error del servidor se muestra junto a su campo.
  function marcarCampos(error: Error) {
    if (!(error instanceof ApiError)) return;
    for (const [campo, mensaje] of Object.entries(error.campos)) {
      const destino = CAMPOS_API[campo];
      if (destino) form.setError(destino, { message: mensaje });
    }
  }

  const enviar = form.handleSubmit((datos) => {
    setPublicado(undefined);
    setResumen(undefined);
    publicar.reset();
    publicarSerie.reset();
    if (datos.repite) {
      publicarSerie.mutate(aSerieApi(datos), {
        onSuccess: (serie) => {
          form.reset(VACIO);
          setResumen({ serie, dias: datos.dias });
          toast.success(
            `Publicamos ${serie.creados.length} ${serie.creados.length === 1 ? "vuelo" : "vuelos"}.`,
          );
        },
        onError: marcarCampos,
      });
      return;
    }
    publicar.mutate(aEntradaApi(datos), {
      onSuccess: (vuelo) => {
        form.reset(VACIO);
        setPublicado(
          `Publicamos el vuelo ${vuelo.codigo} (${vuelo.origen.nombre} → ${vuelo.destino.nombre}). Ya tiene su noticia y su imagen en el carrusel.`,
        );
        toast.success(`Publicamos el vuelo ${vuelo.codigo}.`);
      },
      onError: marcarCampos,
    });
  });

  const error = publicar.error ?? publicarSerie.error;
  const errorGeneral =
    error && !(error instanceof ApiError && Object.keys(error.campos).length > 0)
      ? error.message
      : null;
  const enCurso = publicar.isPending || publicarSerie.isPending;

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
            {resumen && <ResumenSerie serie={resumen.serie} dias={resumen.dias} />}
            {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

            <CamposVuelo repite={repite} />

            <Card aria-labelledby="titulo-repite" className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3">
                <h2 id="titulo-repite" className="sta-panel-title">
                  Se repite
                </h2>
                <Switch
                  checked={repite}
                  onCheckedChange={alCambiarRepite}
                  aria-labelledby="titulo-repite"
                />
              </div>
              {repite && (
                <>
                  <CampoFichas<Entrada> name="dias" label="Días" opciones={DIAS} />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <CampoTexto<Entrada>
                      name="desde"
                      label="Desde"
                      type="date"
                      min={hoy()}
                      max={maximoHasta()}
                    />
                    <CampoTexto<Entrada>
                      name="hasta"
                      label="Hasta"
                      type="date"
                      min={valores.desde || hoy()}
                      max={maximoHasta()}
                      ayuda="Máximo 12 meses desde hoy."
                    />
                  </div>
                </>
              )}
            </Card>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" variant="primary" disabled={enCurso}>
                {enCurso ? "Publicando…" : repite ? "Publicar vuelos" : "Publicar vuelo"}
              </Button>
              <Button variant="secondary" href="/admin/vuelos">
                Cancelar
              </Button>
            </div>
          </form>
        </Form>

        <VistaPrevia
          entrada={vistaEspera && "vuelo" in vistaEspera ? vistaEspera.vuelo : null}
          serie={
            repite ? (vistaEspera && "serie" in vistaEspera ? vistaEspera.serie : null) : undefined
          }
          precio={parseado.success ? parseado.data.precio_economica : 0}
        />
      </div>
    </div>
  );
}
