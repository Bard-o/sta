import type { Schemas } from "@/api/client";
import { fechaCalendario, fechaHora } from "@/lib/format";
import { Notice } from "@/components/ui/notice";
import { frasesOmitidas, patronDias } from "./resumen";
import type { SerieSalida } from "./api";

/** Resumen final de HU-14: los vuelos creados y las fechas omitidas con su motivo. */
export function ResumenSerie({ serie, dias }: { serie: SerieSalida; dias: readonly string[] }) {
  const { creados, omitidas } = serie;
  const ruta = creados[0] ? `${creados[0].origen.nombre} → ${creados[0].destino.nombre}` : "";
  return (
    <Notice tone="info">
      <div className="flex flex-col gap-2">
        <p>
          <strong>
            {creados.length === 0
              ? "No se creó ningún vuelo."
              : `Publicamos ${creados.length} ${creados.length === 1 ? "vuelo" : "vuelos"} (${ruta}) ${patronDias(dias)}.`}
          </strong>{" "}
          {frasesOmitidas(omitidas).join(" ")} Cada vuelo tiene su código y su noticia en el
          carrusel.
        </p>
        {creados.length > 0 && (
          <section aria-label="Vuelos creados">
            <h3 className="label">Vuelos creados</h3>
            <ul className="max-h-48 overflow-auto pl-5 list-disc">
              {creados.map((v: Schemas["Vuelo"]) => (
                <li key={v.id}>
                  {v.codigo} · {fechaHora(v.salida, v.origen.zona_horaria)}
                </li>
              ))}
            </ul>
          </section>
        )}
        {omitidas.length > 0 && (
          <section aria-label="Fechas omitidas">
            <h3 className="label">Fechas omitidas</h3>
            <ul className="max-h-48 overflow-auto pl-5 list-disc">
              {omitidas.map((o) => (
                <li key={o.fecha}>
                  {fechaCalendario(o.fecha)} · {o.motivo}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Notice>
  );
}
