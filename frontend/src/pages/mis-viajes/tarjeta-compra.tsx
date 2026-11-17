import { FlightPass } from "@/components/ui/flight-pass";
import { cop, fechaHora, ZONA_COLOMBIA } from "@/lib/format";
import { datosDelPase } from "../buscar/pase";
import type { Viaje } from "./api";

const NOMBRE_CLASE = { economica: "económica", primera: "primera" } as const;

/** Una compra de S19: sus vuelos, viajeros con silla y clase, y lo que se pagó. Una compra que
 *  viene de pagar una reserva conserva el código de la reserva (HU-27). */
export function TarjetaCompra({ compra }: { compra: Viaje }) {
  const completo = compra.tramos.length === 2;
  return (
    <div className="flex flex-col gap-3" role="group" aria-label={`Compra ${compra.codigo}`}>
      {compra.tramos.map(({ vuelo }, tramo) => {
        const tiquetes = compra.viajeros.flatMap((v) =>
          v.tiquetes.filter((t) => t.tramo === tramo),
        );
        const subtotal = tiquetes.reduce((suma, t) => suma + t.precio, 0);
        return (
          <FlightPass
            key={vuelo.id}
            {...datosDelPase(vuelo)}
            code={tramo === 0 ? `COMPRA ${compra.codigo}` : vuelo.codigo}
            price={cop(tramo === 0 ? compra.total : subtotal)}
            priceNote={tramo === 0 ? (completo ? "Ida y regreso" : undefined) : "Regreso"}
            badges={
              tramo === 0
                ? [
                    {
                      tone: "success",
                      icon: "check",
                      label: compra.estado === "activa" ? "Activa" : "Compra",
                    },
                  ]
                : []
            }
            note={
              tramo === 0 && compra.pagada_en ? (
                <span>Pagada el {fechaHora(compra.pagada_en, ZONA_COLOMBIA)}.</span>
              ) : undefined
            }
          />
        );
      })}
      <ul className="flex flex-col gap-1 px-1">
        {compra.viajeros.map((v) => (
          <li key={v.id} className="body">
            {v.nombres} {v.apellidos}:{" "}
            {v.tiquetes
              .map((t) => `${t.silla}, ${NOMBRE_CLASE[t.clase]}, ${cop(t.precio)}`)
              .join(" · ")}
          </li>
        ))}
      </ul>
    </div>
  );
}
