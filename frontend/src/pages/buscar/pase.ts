import type { FlightPassProps } from "@/components/ui/flight-pass";
import { desfase, duracion, fecha, hora } from "@/lib/format";
import type { VueloBusqueda } from "./api";

/** Lo que el pasabordo muestra de un vuelo, con las horas en la hora local de cada ciudad
 *  (IU-05): código, ruta, salida, llegada, duración y fecha de salida. */
export function datosDelPase(
  vuelo: VueloBusqueda,
): Pick<FlightPassProps, "code" | "from" | "to" | "duration" | "date"> {
  const zo = vuelo.origen.zona_horaria;
  const zd = vuelo.destino.zona_horaria;
  return {
    code: vuelo.codigo,
    from: {
      iata: vuelo.origen.codigo,
      city: vuelo.origen.nombre,
      time: hora(vuelo.salida, zo),
      tz: desfase(vuelo.salida, zo),
    },
    to: {
      iata: vuelo.destino.codigo,
      city: vuelo.destino.nombre,
      time: hora(vuelo.llegada, zd),
      tz: desfase(vuelo.llegada, zd),
    },
    duration: `${duracion(vuelo.duracion_minutos)}, directo`,
    date: `Salida ${fecha(vuelo.salida, zo)}`,
  };
}
