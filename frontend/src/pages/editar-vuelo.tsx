import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { cop, hora } from "@/lib/format";
import { useDebounced } from "@/lib/use-debounced";
import { NoEncontradaPage } from "@/pages/no-encontrada";
import type { VueloEntrada } from "./programar-vuelo/api";
import { CamposVuelo } from "./programar-vuelo/campos-vuelo";
import {
  CAMPOS_API,
  VACIO,
  aEntradaApi,
  esquema,
  type Datos,
  type Entrada,
} from "./programar-vuelo/esquema";
import { VistaPrevia, type Vista } from "./programar-vuelo/vista-previa";
import { useEditarVuelo, useVueloGestion, type VueloAdmin } from "./vuelos-programados/api";

/** Fecha de calendario aaaa-mm-dd de un instante, en la zona dada. */
const diaLocal = (iso: string, zona: string) =>
  new Date(iso).toLocaleDateString("sv-SE", { timeZone: zona });

/** El vuelo como lo escribió quien lo programó: fecha y hora locales del origen, duración en
 *  horas y minutos, precios con formato de pesos. */
function datosIniciales(v: VueloAdmin): Entrada {
  const zona = v.origen.zona_horaria;
  return {
    ...VACIO,
    origen: v.origen.codigo,
    destino: v.destino.codigo,
    fecha_salida: diaLocal(v.salida, zona),
    hora_salida: hora(v.salida, zona),
    horas: String(Math.floor(v.duracion_minutos / 60)),
    minutos: String(v.duracion_minutos % 60),
    precio_economica: cop(v.precio_economica),
    precio_primera: cop(v.precio_primera),
  };
}

/** Lo que ya se sabe del vuelo, con la forma de la vista previa. */
const comoVista = (v: VueloAdmin): Vista => ({
  tipo: v.tipo,
  origen: v.origen,
  destino: v.destino,
  salida: v.salida,
  llegada: v.llegada,
  duracion_minutos: v.duracion_minutos,
  capacidad: v.capacidad,
});

function Formulario({ vuelo }: { vuelo: VueloAdmin }) {
  const navigate = useNavigate();
  const editar = useEditarVuelo(vuelo.id);
  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: datosIniciales(vuelo),
  });

  const valores = useWatch({ control: form.control }) as Entrada;
  const parseado = esquema.safeParse(valores);
  const claveVista = useDebounced(
    parseado.success ? JSON.stringify(aEntradaApi(parseado.data)) : null,
  );
  const entradaVista = useMemo(
    () => (claveVista ? (JSON.parse(claveVista) as VueloEntrada) : null),
    [claveVista],
  );

  // Si solo cambian los precios, la salida y la llegada son las que ya tiene el vuelo.
  const original = datosIniciales(vuelo);
  const mismaSalida =
    entradaVista !== null &&
    entradaVista.origen === original.origen &&
    entradaVista.destino === original.destino &&
    entradaVista.fecha_salida === original.fecha_salida &&
    entradaVista.hora_salida === original.hora_salida &&
    entradaVista.duracion_minutos === vuelo.duracion_minutos;

  const guardar = form.handleSubmit((datos) =>
    editar.mutate(aEntradaApi(datos), {
      onSuccess: () => {
        toast.success(`Guardamos los cambios de ${vuelo.codigo}.`);
        void navigate("/admin/vuelos");
      },
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        // IU-07: cada error del servidor se muestra junto a su campo.
        for (const [campo, mensaje] of Object.entries(error.campos)) {
          const destino = CAMPOS_API[campo];
          if (destino) form.setError(destino, { message: mensaje });
        }
      },
    }),
  );

  const error = editar.error;
  const errorGeneral =
    error && !(error instanceof ApiError && Object.keys(error.campos).length > 0)
      ? error.message
      : null;

  return (
    <div className="grid items-start gap-8 lg:grid-cols-2">
      <Form {...form}>
        <form onSubmit={guardar} noValidate className="flex flex-col gap-4">
          {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}
          <CamposVuelo />
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={editar.isPending}>
              {editar.isPending ? "Guardando…" : "Guardar cambios"}
            </Button>
            <Button variant="secondary" href="/admin/vuelos">
              Cancelar
            </Button>
          </div>
        </form>
      </Form>

      <VistaPrevia
        entrada={entradaVista}
        codigo={vuelo.codigo}
        conocida={mismaSalida ? comoVista(vuelo) : undefined}
        precio={parseado.success ? parseado.data.precio_economica : 0}
      />
    </div>
  );
}

/** S09 · Editar vuelo (HU-15): mismo formulario que programar, con los datos del vuelo. Un vuelo
 *  con reservas activas, con compras o que ya no está programado no se edita: se dice el motivo. */
export function EditarVueloPage() {
  const { vueloId } = useParams();
  const id = Number(vueloId);
  const consulta = useVueloGestion(id);

  const noExiste =
    !Number.isInteger(id) ||
    id <= 0 ||
    (consulta.isError && consulta.error instanceof ApiError && consulta.error.status === 404);
  if (noExiste) return <NoEncontradaPage />;

  const vuelo = consulta.data;
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">{vuelo ? `Editar vuelo ${vuelo.codigo}` : "Editar vuelo"}</h1>
        <p className="sta-sub">
          El código se conserva. Si cambian la ruta, la salida o la duración, se recalculan el tipo,
          la capacidad y la llegada.
        </p>
      </div>

      {consulta.isPending && (
        <p role="status" className="body sta-muted">
          Cargando el vuelo…
        </p>
      )}
      {consulta.isError && <Notice tone="danger">{consulta.error.message}</Notice>}

      {vuelo && !vuelo.editable && (
        <>
          <Notice tone="danger">
            Este vuelo no se puede editar.{" "}
            {vuelo.motivo_no_editable ?? "Ya salió, se realizó o está cancelado."}
          </Notice>
          <div>
            <Button variant="secondary" href="/admin/vuelos">
              Volver a vuelos programados
            </Button>
          </div>
        </>
      )}
      {vuelo?.editable && <Formulario key={vuelo.id} vuelo={vuelo} />}
    </div>
  );
}
