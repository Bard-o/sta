import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { RUTA_VERIFICACION } from "@/auth/verificacion";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { FlightPass } from "@/components/ui/flight-pass";
import { Notice } from "@/components/ui/notice";
import { cop, fechaHora, ZONA_COLOMBIA } from "@/lib/format";
import { datosDelPase } from "../buscar/pase";
import { usePagarReserva, type Viaje } from "./api";
import { textoRestante, useAhora } from "./tiempo";

type Viajero = Viaje["viajeros"][number];

const nombre = (v: Viajero) => `${v.nombres} ${v.apellidos}`;
const sillas = (v: Viajero) => v.tiquetes.map((t) => t.silla).join(" y ");
const pendiente = (v: Viajero) => v.tiquetes.some((t) => t.estado === "reservado");
const valorPendiente = (v: Viajero) =>
  v.tiquetes.filter((t) => t.estado === "reservado").reduce((suma, t) => suma + t.precio, 0);

/** Una reserva de S19 (HU-27): sus vuelos como pasabordo, cuánto falta para que venza, el precio
 *  congelado y, si está vigente, la elección de quién se paga. Pagar 2 de 4 deja los otros 2
 *  reservados con el mismo vencimiento (SUP-40). Vencida o cancelada no ofrece pagar. */
export function TarjetaReserva({
  reserva,
  saldo,
  destacada,
}: {
  reserva: Viaje;
  saldo: number | undefined;
  /** Llegó de recargar (`?pagar=<id>`): se muestra marcada y a la vista para seguir pagando. */
  destacada: boolean;
}) {
  const pagar = usePagarReserva(reserva.id);
  const ahora = useAhora();
  const [desmarcados, setDesmarcados] = useState<Set<number>>(new Set());
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (destacada) ref.current?.scrollIntoView?.({ block: "center" });
  }, [destacada]);

  const vence = reserva.vence_en;
  const venceYa = vence !== null && Date.parse(vence) <= ahora;
  const vigente = reserva.estado === "vigente" && !venceYa;
  const pendientes = reserva.viajeros.filter(pendiente);
  const elegidos = pendientes.filter((v) => !desmarcados.has(v.id));
  const monto = elegidos.reduce((suma, v) => suma + valorPendiente(v), 0);
  const faltante = saldo === undefined ? 0 : Math.max(0, monto - saldo);
  const completo = reserva.tramos.length === 2;

  const volver = `/mis-viajes?tipo=reserva&pagar=${reserva.id}`;
  const urlRecarga = `/monedero/recargar?faltante=${faltante}&codigo=${encodeURIComponent(reserva.codigo)}&volver=${encodeURIComponent(volver)}`;

  const error = pagar.error;
  const sinVerificar = error instanceof ApiError && error.codigo === "correo_no_verificado";
  // El error de los viajeros elegidos (`campos.viajero_ids`) trae el texto exacto del contrato.
  const mensaje =
    error && !sinVerificar
      ? (error instanceof ApiError && error.campos.viajero_ids) || error.message
      : null;

  function alternar(id: number) {
    setDesmarcados((previos) => {
      const siguiente = new Set(previos);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });
  }

  function pagarElegidos() {
    pagar.mutate(
      elegidos.map((v) => v.id),
      {
        onSuccess: () => {
          // Los que quedan reservados vuelven a salir elegidos para el siguiente pago.
          setDesmarcados(new Set());
          toast.success(
            `Pagamos ${elegidos.length} ${elegidos.length === 1 ? "viajero" : "viajeros"} de la reserva ${reserva.codigo}. Enviamos el código a los viajeros y el comprobante a tu correo.`,
          );
        },
      },
    );
  }

  const estado = vigente ? (
    <span>
      <strong>Vence en {textoRestante(vence!, ahora)}</strong> ({fechaHora(vence!, ZONA_COLOMBIA)}).
      Precio congelado.
    </span>
  ) : reserva.estado === "pagada" ? (
    <span>Pagada completa.</span>
  ) : reserva.estado === "cancelada" ? (
    <span>Cancelada.</span>
  ) : (
    <span>Vencida el {fechaHora(vence ?? reserva.creada_en, ZONA_COLOMBIA)}.</span>
  );
  const insignia = vigente
    ? { tone: "info" as const, icon: "tag" as const, label: "Vigente" }
    : reserva.estado === "pagada"
      ? { tone: "success" as const, icon: "check" as const, label: "Pagada" }
      : reserva.estado === "cancelada"
        ? { tone: "danger" as const, icon: "x" as const, label: "Cancelada" }
        : { tone: "danger" as const, icon: "x" as const, label: "Vencida" };

  return (
    <div
      ref={ref}
      className="flex flex-col gap-3"
      role="group"
      aria-label={`Reserva ${reserva.codigo}`}
    >
      <div className="flex flex-col gap-3">
        {reserva.tramos.map(({ vuelo }, tramo) => {
          const primero = tramo === 0;
          const subtotal = reserva.viajeros
            .filter((v) => (vigente ? elegidos.includes(v) : true))
            .reduce(
              (suma, v) => suma + (v.tiquetes.find((t) => t.tramo === tramo)?.precio ?? 0),
              0,
            );
          return (
            <FlightPass
              key={vuelo.id}
              {...datosDelPase(vuelo)}
              code={primero ? `RES ${reserva.codigo}` : vuelo.codigo}
              price={cop(primero ? (vigente ? monto : reserva.total) : subtotal)}
              priceNote={
                primero
                  ? vigente
                    ? `${elegidos.length} de ${pendientes.length} seleccionados${completo ? ", ida y regreso" : ""}`
                    : completo
                      ? "Ida y regreso"
                      : undefined
                  : "Regreso"
              }
              badges={primero ? [insignia] : []}
              note={primero ? estado : undefined}
              state={destacada ? "selected" : vigente ? "default" : "soldout"}
              action={
                primero && vigente ? (
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={elegidos.length === 0 || pagar.isPending || faltante > 0}
                    onClick={pagarElegidos}
                  >
                    {pagar.isPending
                      ? "Pagando…"
                      : `Pagar ${elegidos.length} ${elegidos.length === 1 ? "viajero" : "viajeros"}`}
                    <span className="sr-only"> de la reserva {reserva.codigo}</span>
                  </Button>
                ) : undefined
              }
            />
          );
        })}
      </div>

      <fieldset className="flex flex-col gap-2 px-1">
        <legend className="sr-only">Viajeros de la reserva {reserva.codigo}</legend>
        <ul className="flex flex-wrap gap-x-6 gap-y-2">
          {reserva.viajeros.map((v) => (
            <li key={v.id}>
              {vigente && pendiente(v) ? (
                <label className="flex items-center gap-2">
                  <Checkbox checked={!desmarcados.has(v.id)} onChange={() => alternar(v.id)} />
                  <span className="body">
                    {nombre(v)}, {sillas(v)}
                  </span>
                </label>
              ) : (
                <span className="body sta-muted">
                  {nombre(v)}, {sillas(v)}
                  {v.tiquetes.some((t) => t.estado === "comprado") ? " (pagado)" : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      </fieldset>

      {vigente && pendientes.length > 1 && (
        <p className="caption sta-muted">
          Si pagas solo algunos viajeros, los demás siguen reservados con el mismo vencimiento.
        </p>
      )}
      {vigente && faltante > 0 && (
        <Notice tone="danger">
          <div className="flex flex-col items-start gap-2">
            <span>
              Te faltan {cop(faltante)}. Recarga tu monedero y vuelve a pagar esta reserva.
            </span>
            <Button size="sm" href={urlRecarga}>
              Recargar {cop(faltante)}
            </Button>
          </div>
        </Notice>
      )}
      {sinVerificar && (
        <Notice tone="danger">
          <div className="flex flex-col items-start gap-1">
            <span>Verifica tu correo para reservar o comprar.</span>
            <Link className="sta-link" to={RUTA_VERIFICACION}>
              Reenviar la verificación
            </Link>
          </div>
        </Notice>
      )}
      {mensaje && <Notice tone="danger">{mensaje}</Notice>}
    </div>
  );
}
