import { useMemo } from "react";
import { useWatch } from "react-hook-form";
import { CampoDinero, CampoLista, CampoTexto } from "@/components/ui/campos";
import { Notice } from "@/components/ui/notice";
import { desfase } from "@/lib/format";
import { hoy } from "@/lib/persona";
import { useCiudades } from "./api";
import type { Entrada } from "./esquema";

/** Los campos de un vuelo (HU-13, HU-15): ruta, salida, duración y precios. Se usa dentro de un
 *  `<Form>` del tipo `Entrada`. Con `repite` la fecha de salida la reemplaza el periodo. */
export function CamposVuelo({ repite = false }: { repite?: boolean }) {
  const ciudades = useCiudades();
  const [codigoOrigen, fechaSalida, desde] = useWatch<Entrada, ["origen", "fecha_salida", "desde"]>(
    {
      name: ["origen", "fecha_salida", "desde"],
    },
  );

  const opciones = useMemo(
    () =>
      [...(ciudades.data ?? [])]
        .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"))
        .map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.codigo})` })),
    [ciudades.data],
  );
  const origen = ciudades.data?.find((c) => c.codigo === codigoOrigen);
  const diaReferencia = repite ? desde : fechaSalida;
  const etiquetaHora = origen
    ? `Hora de salida (hora de ${origen.nombre}, ${desfase(
        /^\d{4}-\d{2}-\d{2}$/.test(diaReferencia)
          ? new Date(`${diaReferencia}T12:00:00Z`)
          : new Date(),
        origen.zona_horaria,
      )})`
    : "Hora de salida (hora local del origen)";

  return (
    <>
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
        {!repite && (
          <CampoTexto<Entrada>
            name="fecha_salida"
            label="Fecha de salida"
            type="date"
            min={hoy()}
          />
        )}
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
    </>
  );
}
