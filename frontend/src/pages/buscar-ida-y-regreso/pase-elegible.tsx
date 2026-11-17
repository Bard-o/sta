import { Button } from "@/components/ui/button";
import { FlightPass } from "@/components/ui/flight-pass";
import { cop } from "@/lib/format";
import type { VueloBusqueda } from "../buscar/api";
import { datosDelPase } from "../buscar/pase";
import type { Clase } from "./esquema";

const CLASES: Clase[] = ["economica", "primera"];
const ETIQUETA: Record<Clase, string> = { economica: "Económica", primera: "Primera clase" };

/** Un vuelo del paso 1 o 2 como pasabordo que se puede elegir. El elegido lleva «Elegido», el
 *  borde de tinta y los botones para escoger la clase de ese tramo (RF-40, HU-26); uno que no se
 *  puede elegir (agotado o que sale antes de la llegada) dice por qué. */
export function PaseElegible({
  vuelo,
  tramo,
  elegido,
  clase,
  motivoNoElegible,
  onElegir,
  onClase,
}: {
  vuelo: VueloBusqueda;
  /** «ida» o «regreso»: va en el nombre accesible de los botones. */
  tramo: "ida" | "regreso";
  elegido: boolean;
  /** La clase elegida en este tramo (solo si el vuelo está elegido). */
  clase: Clase | "";
  motivoNoElegible?: string;
  onElegir: () => void;
  onClase: (clase: Clase) => void;
}) {
  const agotado = vuelo.agotado;
  const bloqueado = agotado || motivoNoElegible !== undefined;
  // Se muestra el precio de la clase elegida; sin elegir, el de económica (o primera si no hay).
  const mostrada: Clase =
    clase || (vuelo.economica.agotada && !vuelo.primera.agotada ? "primera" : "economica");
  const datos = vuelo[mostrada];

  return (
    <FlightPass
      {...datosDelPase(vuelo)}
      state={elegido ? "selected" : bloqueado ? "soldout" : "default"}
      badges={[
        ...(elegido
          ? [{ tone: "success" as const, icon: "check" as const, label: "Elegido" }]
          : []),
        ...(agotado ? [{ tone: "danger" as const, icon: "x" as const, label: "Agotado" }] : []),
      ]}
      note={
        motivoNoElegible ?? (
          <span className="inline-flex flex-wrap items-center gap-2">
            {elegido ? (
              <span
                role="group"
                aria-label={`Clase de la ${tramo}`}
                className="inline-flex flex-wrap gap-2"
              >
                {CLASES.map((c) => (
                  <Button
                    key={c}
                    size="sm"
                    variant={clase === c ? "primary" : "secondary"}
                    aria-pressed={clase === c}
                    disabled={vuelo[c].agotada}
                    onClick={() => onClase(c)}
                  >
                    {ETIQUETA[c]}
                    <span className="sr-only">
                      {" "}
                      {cop(vuelo[c].precio_vigente)}
                      {vuelo[c].agotada ? ", agotada" : ""}
                    </span>
                  </Button>
                ))}
              </span>
            ) : (
              CLASES.map((c) => (
                <span key={c}>
                  {ETIQUETA[c]}: {vuelo[c].agotada ? "agotada" : `quedan ${vuelo[c].disponibles}`}
                </span>
              ))
            )}
          </span>
        )
      }
      oldPrice={datos.promocion ? cop(datos.precio_base) : undefined}
      price={cop(datos.precio_vigente)}
      priceNote={`${ETIQUETA[mostrada]} · por viajero`}
      action={
        bloqueado || elegido ? undefined : (
          <Button size="sm" variant="primary" onClick={onElegir}>
            Elegir{" "}
            <span className="sr-only">
              {vuelo.codigo} como {tramo}
            </span>
          </Button>
        )
      }
    />
  );
}
