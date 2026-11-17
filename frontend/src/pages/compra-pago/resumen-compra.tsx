import { FlightPass } from "@/components/ui/flight-pass";
import { cop } from "@/lib/format";
import { datosDelPase } from "../buscar/pase";
import type { Compra } from "./api";

const lista = (items: string[]) =>
  items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} y ${items.at(-1)}`;

const NOMBRE_CLASE = { economica: "económica", primera: "primera" } as const;

/** El resumen de la compra como pasabordo, uno por tramo (HU-25, HU-26): quién viaja, las sillas
 *  asignadas y lo que cuesta ese tramo. Un trayecto completo se paga junto, con un solo código. */
export function ResumenCompra({ compra }: { compra: Compra }) {
  const completo = compra.tramos.length === 2;
  return (
    <div className="flex flex-col gap-4">
      {compra.tramos.map(({ vuelo }, tramo) => {
        const tiquetes = compra.viajeros.map((v) => ({
          viajero: `${v.nombres} ${v.apellidos}`,
          tiquete: v.tiquetes.find((t) => t.tramo === tramo),
        }));
        const sillas = tiquetes.flatMap(({ tiquete }) => (tiquete ? [tiquete.silla] : []));
        const subtotal = tiquetes.reduce((suma, { tiquete }) => suma + (tiquete?.precio ?? 0), 0);
        const precios = new Set(tiquetes.map(({ tiquete }) => tiquete?.precio));
        const clases = new Set(tiquetes.map(({ tiquete }) => tiquete?.clase));
        const unitario = [...precios][0];
        return (
          <div key={vuelo.id} className="flex flex-col gap-2">
            {completo && (
              <span className="overline sta-muted">{tramo === 0 ? "IDA" : "REGRESO"}</span>
            )}
            <FlightPass
              {...datosDelPase(vuelo)}
              price={cop(subtotal)}
              priceNote={
                precios.size === 1 && unitario !== undefined
                  ? `${tiquetes.length} × ${cop(unitario)}${
                      clases.size === 1 ? `, ${NOMBRE_CLASE[[...clases][0]!]}` : ""
                    }`
                  : "Total del tramo"
              }
              note={
                <span>
                  {lista(tiquetes.map((t) => t.viajero))}.{" "}
                  {sillas.length === 1 ? "Silla" : "Sillas"} <strong>{lista(sillas)}</strong>.
                </span>
              }
            />
          </div>
        );
      })}
    </div>
  );
}
