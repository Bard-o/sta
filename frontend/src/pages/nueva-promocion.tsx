import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { CampoFichas, CampoTexto } from "@/components/ui/campos";
import { FlightPass } from "@/components/ui/flight-pass";
import { Form } from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { cop, desfase, duracion, fecha, hora } from "@/lib/format";
import { precioConDescuento } from "@/lib/promocion";
import { NoEncontradaPage } from "@/pages/no-encontrada";
import { useCrearPromocion } from "./promociones/api";
import {
  CAMPOS_API,
  CLASES,
  VACIO,
  aEntradaApi,
  esquema,
  porcentajeValido,
  type Datos,
  type Entrada,
} from "./promociones/esquema";
import { useVueloGestion, type VueloAdmin } from "./vuelos-programados/api";
import { OcupacionPorClase } from "./vuelos-programados/ocupacion";

const sillas = (n: number) => `${n} ${n === 1 ? "silla disponible" : "sillas disponibles"}`;

/** El vuelo como pasabordo, con el precio base de económica. */
function PaseDelVuelo({ vuelo }: { vuelo: VueloAdmin }) {
  const zo = vuelo.origen.zona_horaria;
  const zd = vuelo.destino.zona_horaria;
  return (
    <FlightPass
      code={vuelo.codigo}
      from={{
        iata: vuelo.origen.codigo,
        city: vuelo.origen.nombre,
        time: hora(vuelo.salida, zo),
        tz: desfase(vuelo.salida, zo),
      }}
      to={{
        iata: vuelo.destino.codigo,
        city: vuelo.destino.nombre,
        time: hora(vuelo.llegada, zd),
        tz: desfase(vuelo.llegada, zd),
      }}
      duration={`${duracion(vuelo.duracion_minutos)}, directo`}
      date={`Salida ${fecha(vuelo.salida, zo)}`}
      price={cop(vuelo.precio_economica)}
      priceNote="Económica"
    />
  );
}

/** «Económica pasa de $ 2.450.000 a $ 1.470.000 para las 142 sillas disponibles.» */
function Resumen({ vuelo, valores }: { vuelo: VueloAdmin; valores: Entrada }) {
  const porcentaje = porcentajeValido(valores.porcentaje);
  if (porcentaje === null || valores.clases.length === 0) return null;
  return (
    <Notice tone="info">
      <div className="flex flex-col gap-1">
        {CLASES.filter((c) => valores.clases.includes(c.value)).map((c) => {
          const base = c.value === "economica" ? vuelo.precio_economica : vuelo.precio_primera;
          const disponibles = vuelo.ocupacion[c.value].disponibles;
          return (
            <p key={c.value}>
              {c.label} pasa de <s>{cop(base)}</s> a{" "}
              <strong>{cop(precioConDescuento(base, porcentaje))}</strong> para{" "}
              {disponibles === 1 ? "la" : "las"} {sillas(disponibles)}.
            </p>
          );
        })}
      </div>
    </Notice>
  );
}

function Formulario({ vuelo }: { vuelo: VueloAdmin }) {
  const navigate = useNavigate();
  const crear = useCrearPromocion(vuelo.id);
  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: VACIO,
  });
  const valores = useWatch({ control: form.control }) as Entrada;

  const publicar = form.handleSubmit((datos) =>
    crear.mutate(aEntradaApi(datos), {
      onSuccess: (promocion) => {
        toast.success(`Publicamos la promoción del ${promocion.porcentaje} % en ${vuelo.codigo}.`);
        void navigate("/admin/promociones");
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

  // Una promoción repetida en una clase se explica con el mensaje completo del servidor.
  const error = crear.error;
  const aviso =
    error &&
    (!(error instanceof ApiError) ||
      error.codigo === "promocion_duplicada" ||
      Object.keys(error.campos).length === 0)
      ? error.message
      : null;

  return (
    <Glass title="Descuento">
      <Form {...form}>
        <form onSubmit={publicar} noValidate className="flex flex-col gap-4">
          <CampoTexto<Entrada>
            name="porcentaje"
            label="Porcentaje"
            inputMode="numeric"
            autoComplete="off"
            ayuda="Entre 1 % y 90 %."
          />
          <CampoFichas<Entrada> name="clases" label="Clase" opciones={CLASES} />
          <div className="grid gap-3 sm:grid-cols-2">
            <CampoTexto<Entrada>
              name="inicio"
              label="Inicio (hora de Colombia)"
              type="datetime-local"
              ayuda="Si ya pasó, la promoción empieza de inmediato."
            />
            <CampoTexto<Entrada> name="fin" label="Fin (hora de Colombia)" type="datetime-local" />
          </div>
          <Resumen vuelo={vuelo} valores={valores} />
          {aviso && <Notice tone="danger">{aviso}</Notice>}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={crear.isPending}>
              {crear.isPending ? "Publicando…" : "Publicar promoción"}
            </Button>
            <Button variant="secondary" href="/admin/vuelos">
              Cancelar
            </Button>
          </div>
        </form>
      </Form>
    </Glass>
  );
}

/** S11 · Nueva promoción (HU-17) para un vuelo programado. */
export function NuevaPromocionPage() {
  const { vueloId } = useParams();
  const id = Number(vueloId);
  const consulta = useVueloGestion(id);
  const [ahora] = useState(() => Date.now());

  const noExiste =
    !Number.isInteger(id) ||
    id <= 0 ||
    (consulta.isError && consulta.error instanceof ApiError && consulta.error.status === 404);
  if (noExiste) return <NoEncontradaPage />;

  const vuelo = consulta.data;
  // Un vuelo que ya salió, se realizó o se canceló no admite promociones (RF-23).
  const cerrado = vuelo
    ? vuelo.estado !== "programado" || Date.parse(vuelo.salida) <= ahora
    : false;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">Nueva promoción</h1>
        <p className="sta-sub">
          Aplica solo a las sillas disponibles. Termina en la fecha de fin o cuando se agoten, lo
          que ocurra primero.
        </p>
      </div>

      {consulta.isPending && (
        <p role="status" className="body sta-muted">
          Cargando el vuelo…
        </p>
      )}
      {consulta.isError && <Notice tone="danger">{consulta.error.message}</Notice>}

      {vuelo && cerrado && (
        <>
          <Notice tone="danger">
            El vuelo {vuelo.codigo} ya salió, se realizó o está cancelado: no admite promociones.
          </Notice>
          <div>
            <Button variant="secondary" href="/admin/vuelos">
              Volver a vuelos programados
            </Button>
          </div>
        </>
      )}

      {vuelo && !cerrado && (
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <PaseDelVuelo vuelo={vuelo} />
            <Glass title="Ventas del vuelo">
              <OcupacionPorClase ocupacion={vuelo.ocupacion} />
            </Glass>
          </div>
          <Formulario key={vuelo.id} vuelo={vuelo} />
        </div>
      )}
    </div>
  );
}
