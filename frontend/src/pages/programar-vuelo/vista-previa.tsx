import type { ReactNode } from "react";
import { ApiError, type Schemas } from "@/api/client";
import { FlightPass } from "@/components/ui/flight-pass";
import { Notice } from "@/components/ui/notice";
import { cop, desfase, duracion, fecha, hora } from "@/lib/format";
import { useVistaPrevia, useVistaSerie, type SerieEntrada, type VueloEntrada } from "./api";
import { resumenSerie } from "./resumen";

export type Vista = Schemas["VueloVistaPrevia"];

const NOMBRE_CAMPO: Record<string, string> = {
  origen: "Origen",
  destino: "Destino",
  fecha_salida: "Fecha de salida",
  hora_salida: "Hora de salida",
  duracion_minutos: "Duración",
  precio_economica: "Precio económica",
  precio_primera: "Precio primera",
  dias_semana: "Días",
  desde: "Desde",
  hasta: "Hasta",
};

function Pase({
  vista,
  precio,
  codigo,
  extra,
}: {
  vista: Vista;
  precio: number;
  codigo: string;
  extra?: ReactNode;
}) {
  const zo = vista.origen.zona_horaria;
  const zd = vista.destino.zona_horaria;
  return (
    <>
      <FlightPass
        code={codigo}
        from={{
          iata: vista.origen.codigo,
          city: vista.origen.nombre,
          time: hora(vista.salida, zo),
          tz: desfase(vista.salida, zo),
        }}
        to={{
          iata: vista.destino.codigo,
          city: vista.destino.nombre,
          time: hora(vista.llegada, zd),
          tz: desfase(vista.llegada, zd),
        }}
        duration={`${duracion(vista.duracion_minutos)}, directo`}
        date={`Salida ${fecha(vista.salida, zo)}`}
        price={cop(precio)}
        priceNote="Económica desde"
      />
      <div className="sta-notice" style={{ display: "block" }}>
        <p>
          <strong>Tipo:</strong> {vista.tipo}, {vista.capacidad.total} sillas (
          {vista.capacidad.primera} en primera, {vista.capacidad.economica} en económica).
        </p>
        <p>
          <strong>Llegada calculada:</strong> {fecha(vista.llegada, zd)} {hora(vista.llegada, zd)}{" "}
          en {vista.destino.nombre} ({desfase(vista.llegada, zd)}).
        </p>
        {extra}
      </div>
    </>
  );
}

function Errores({ error }: { error: Error }) {
  return (
    <Notice tone="danger">
      {error.message}
      {error instanceof ApiError && Object.keys(error.campos).length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {Object.entries(error.campos).map(([campo, mensaje]) => (
            <li key={campo}>
              {NOMBRE_CAMPO[campo] ?? campo}: {mensaje}
            </li>
          ))}
        </ul>
      )}
    </Notice>
  );
}

/** Un vuelo nuevo aún no tiene código: se asigna al guardar. */
const CODIGO_NUEVO = "STA-?????";

const INDICACION =
  "Completa el formulario con datos válidos para ver el pase del vuelo y lo que calcula el sistema.";

function PorVuelo({
  entrada,
  precio,
  codigo = CODIGO_NUEVO,
  conocida,
  extra,
}: {
  entrada: VueloEntrada | null;
  precio: number;
  codigo?: string;
  conocida?: Vista;
  extra?: ReactNode;
}) {
  // Con `conocida` no se consulta: el servidor la rechazaría como duplicada de sí misma.
  const consulta = useVistaPrevia(conocida ? null : entrada);
  if (conocida) {
    return <Pase vista={conocida} precio={precio} codigo={codigo} extra={extra} />;
  }
  return (
    <>
      {entrada === null && <p className="body sta-muted">{INDICACION}</p>}
      {entrada !== null && consulta.isPending && (
        <p role="status" className="body sta-muted">
          Calculando la vista previa…
        </p>
      )}
      {entrada !== null && consulta.isError && <Errores error={consulta.error} />}
      {entrada !== null && consulta.data && (
        <Pase vista={consulta.data} precio={precio} codigo={codigo} extra={extra} />
      )}
    </>
  );
}

/** Con «Se repite»: el pase es el de la primera fecha que se crearía y se suma el resumen. */
function PorSerie({ serie, precio }: { serie: SerieEntrada | null; precio: number }) {
  const consulta = useVistaSerie(serie);
  if (serie === null) return <p className="body sta-muted">{INDICACION}</p>;
  if (consulta.isPending) {
    return (
      <p role="status" className="body sta-muted">
        Calculando la vista previa…
      </p>
    );
  }
  if (consulta.isError) return <Errores error={consulta.error} />;

  const { fechas, omitidas } = consulta.data;
  const repeticiones = (
    <p>
      <strong>Repeticiones:</strong> {resumenSerie(fechas.length, omitidas, serie.dias_semana)}
    </p>
  );
  const vuelo: VueloEntrada = {
    origen: serie.origen,
    destino: serie.destino,
    fecha_salida: fechas[0] ?? "",
    hora_salida: serie.hora_salida,
    duracion_minutos: serie.duracion_minutos,
    precio_economica: serie.precio_economica,
    precio_primera: serie.precio_primera,
  };

  if (fechas.length === 0) {
    return (
      <div className="sta-notice" style={{ display: "block" }}>
        {repeticiones}
        <p>Con estos datos no se crearía ningún vuelo: cambia los días o el periodo.</p>
      </div>
    );
  }
  return <PorVuelo entrada={vuelo} precio={precio} extra={repeticiones} />;
}

/** «Así lo verá el cliente» (S08): el pase del vuelo y lo que el sistema calcula, antes de guardar.
 *  Con `serie` (el vuelo se repite) muestra además cuántos vuelos se crearían. */
export function VistaPrevia({
  entrada,
  serie,
  precio,
  codigo,
  conocida,
}: {
  entrada: VueloEntrada | null;
  serie?: SerieEntrada | null;
  precio: number;
  /** Código del vuelo que se edita; sin él se muestra «STA-?????». */
  codigo?: string;
  /** Vista ya conocida (al editar, mientras no cambien ruta, salida ni duración). */
  conocida?: Vista;
}) {
  return (
    <section aria-labelledby="titulo-vista-previa" className="flex flex-col gap-3">
      <h2 id="titulo-vista-previa" className="sta-panel-title">
        Así lo verá el cliente
      </h2>
      {serie === undefined ? (
        <PorVuelo entrada={entrada} precio={precio} codigo={codigo} conocida={conocida} />
      ) : (
        <PorSerie serie={serie} precio={precio} />
      )}
    </section>
  );
}
