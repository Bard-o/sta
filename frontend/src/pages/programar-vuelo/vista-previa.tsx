import { ApiError, type Schemas } from "@/api/client";
import { FlightPass } from "@/components/ui/flight-pass";
import { Notice } from "@/components/ui/notice";
import { cop, desfase, duracion, fecha, hora } from "@/lib/format";
import { useVistaPrevia, type VueloEntrada } from "./api";

type Vista = Schemas["VueloVistaPrevia"];

const NOMBRE_CAMPO: Record<string, string> = {
  origen: "Origen",
  destino: "Destino",
  fecha_salida: "Fecha de salida",
  hora_salida: "Hora de salida",
  duracion_minutos: "Duración",
  precio_economica: "Precio económica",
  precio_primera: "Precio primera",
};

function Pase({ vista, precio }: { vista: Vista; precio: number }) {
  const zo = vista.origen.zona_horaria;
  const zd = vista.destino.zona_horaria;
  return (
    <>
      <FlightPass
        code="STA-?????"
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
      </div>
    </>
  );
}

/** «Así lo verá el cliente» (S08): el pase del vuelo y lo que el sistema calcula, antes de guardar. */
export function VistaPrevia({ entrada, precio }: { entrada: VueloEntrada | null; precio: number }) {
  const consulta = useVistaPrevia(entrada);

  return (
    <section aria-labelledby="titulo-vista-previa" className="flex flex-col gap-3">
      <h2 id="titulo-vista-previa" className="sta-panel-title">
        Así lo verá el cliente
      </h2>
      {entrada === null && (
        <p className="body sta-muted">
          Completa el formulario con datos válidos para ver el pase del vuelo y lo que calcula el
          sistema.
        </p>
      )}
      {entrada !== null && consulta.isPending && (
        <p role="status" className="body sta-muted">
          Calculando la vista previa…
        </p>
      )}
      {entrada !== null && consulta.isError && (
        <Notice tone="danger">
          {consulta.error.message}
          {consulta.error instanceof ApiError && Object.keys(consulta.error.campos).length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {Object.entries(consulta.error.campos).map(([campo, mensaje]) => (
                <li key={campo}>
                  {NOMBRE_CAMPO[campo] ?? campo}: {mensaje}
                </li>
              ))}
            </ul>
          )}
        </Notice>
      )}
      {entrada !== null && consulta.data && <Pase vista={consulta.data} precio={precio} />}
    </section>
  );
}
