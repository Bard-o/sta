import { useState } from "react";
import { useCambiarSeleccion, type SeleccionCarrito } from "@/auth/carrito";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FlightPass } from "@/components/ui/flight-pass";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { cop, desfase, duracion, fecha, fechaHora, hora, ZONA_COLOMBIA } from "@/lib/format";
import { QuitarSeleccionDialogo } from "./quitar-dialogo";

type Tramo = SeleccionCarrito["tramos"][number];
type Clase = Tramo["clase"];

const CLASES: { value: Clase; label: string }[] = [
  { value: "economica", label: "Económica" },
  { value: "primera", label: "Primera clase" },
];
const NOMBRE_CLASE: Record<Clase, string> = { economica: "Económica", primera: "Primera clase" };

/** Máximo de tiquetes activos por cliente en un vuelo (RF-32). El servidor lo vuelve a validar. */
const MAX_VIAJEROS = 5;
const CANTIDADES = Array.from({ length: MAX_VIAJEROS }, (_, i) => String(i + 1));

const viajeros = (n: number) => `${n} ${n === 1 ? "viajero" : "viajeros"}`;

function PaseDelTramo({ tramo, cantidad }: { tramo: Tramo; cantidad: number }) {
  const { vuelo } = tramo;
  const zo = vuelo.origen.zona_horaria;
  const zd = vuelo.destino.zona_horaria;
  const cambioDePrecio = tramo.precio_unitario !== tramo.precio_al_agregar;
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
      badges={
        tramo.promocion_porcentaje
          ? [{ tone: "accent", icon: "tag", label: `Promoción −${tramo.promocion_porcentaje} %` }]
          : []
      }
      oldPrice={cambioDePrecio ? cop(tramo.precio_al_agregar) : undefined}
      price={cop(tramo.precio_unitario)}
      priceNote={`por viajero · ${NOMBRE_CLASE[tramo.clase]}`}
      note={
        tramo.disponibles > 0
          ? `Quedan ${tramo.disponibles} ${tramo.disponibles === 1 ? "silla" : "sillas"}`
          : undefined
      }
      state={tramo.disponibles < cantidad ? "soldout" : "default"}
    />
  );
}

/** Una selección del carrito: uno o dos vuelos (trayecto completo, RF-40), con su clase, su
 *  cantidad de viajeros, sus avisos y la salida hacia los datos de los viajeros (HU-22, HU-23). */
export function SeleccionCard({ seleccion }: { seleccion: SeleccionCarrito }) {
  const cambiar = useCambiarSeleccion();
  const [quitando, setQuitando] = useState(false);
  const completo = seleccion.tramos.length === 2;
  const ocupado = cambiar.isPending;
  const error = cambiar.error;

  const cambiarClase = (indice: number, clase: Clase) => {
    cambiar.mutate({
      id: seleccion.id,
      cambio: { clases: seleccion.tramos.map((t, i) => (i === indice ? clase : t.clase)) },
    });
  };

  return (
    <Glass
      aria-label={
        completo
          ? `Trayecto completo ${seleccion.tramos[0].vuelo.origen.nombre} a ${seleccion.tramos[1].vuelo.destino.nombre}`
          : `Selección ${seleccion.tramos[0].vuelo.codigo}`
      }
      title={completo ? "Trayecto completo, ida y regreso" : undefined}
      actions={
        <Button
          variant="ghost"
          size="sm"
          icon="x"
          disabled={ocupado}
          onClick={() => setQuitando(true)}
          aria-label={`Quitar ${seleccion.tramos.map((t) => t.vuelo.codigo).join(" y ")} del carrito`}
        >
          Quitar
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        {seleccion.tramos.map((tramo, i) => (
          <div key={tramo.vuelo.id} className="flex flex-col gap-3">
            {completo && <span className="overline sta-muted">{i === 0 ? "IDA" : "REGRESO"}</span>}
            <PaseDelTramo tramo={tramo} cantidad={seleccion.viajeros} />
            <Field
              label={completo ? (i === 0 ? "Clase de la ida" : "Clase del regreso") : "Clase"}
              options={CLASES}
              value={tramo.clase}
              disabled={ocupado}
              onChange={(e) => cambiarClase(i, e.target.value as Clase)}
            />
          </div>
        ))}

        <Field
          label="Viajeros"
          options={CANTIDADES}
          value={String(seleccion.viajeros)}
          disabled={ocupado}
          onChange={(e) =>
            cambiar.mutate({ id: seleccion.id, cambio: { viajeros: Number(e.target.value) } })
          }
        />

        {seleccion.avisos.map((aviso) => (
          <Notice
            key={`${aviso.codigo}-${aviso.tramo}`}
            tone={aviso.codigo === "precio_cambio" ? "info" : "danger"}
          >
            {completo && `${aviso.tramo === 0 ? "Ida" : "Regreso"}: `}
            {aviso.mensaje}
          </Notice>
        ))}
        {error && <Notice tone="danger">{error.message}</Notice>}

        <div className="sta-between">
          <div>
            <p className="overline sta-muted">SUBTOTAL</p>
            <p className="price">{cop(seleccion.subtotal)}</p>
            <p className="caption sta-muted">
              {viajeros(seleccion.viajeros)}
              {completo ? ", ida y regreso" : ""}
            </p>
            {seleccion.reserva_venceria_en && (
              <p className="caption sta-muted">
                Si reservas ahora, el precio y las sillas quedan congelados hasta el{" "}
                {fechaHora(seleccion.reserva_venceria_en, ZONA_COLOMBIA)} (hora de Colombia).
              </p>
            )}
          </div>
          {seleccion.confirmable ? (
            <Button variant="primary" href={`/compra/viajeros?seleccion=${seleccion.id}`}>
              Continuar con los viajeros
            </Button>
          ) : (
            <div className="flex flex-col items-end gap-2">
              <Badge tone="danger" icon="alert">
                No se puede continuar
              </Badge>
              <Button variant="primary" disabled>
                Continuar con los viajeros
              </Button>
            </div>
          )}
        </div>
      </div>
      <QuitarSeleccionDialogo
        seleccion={seleccion}
        abierto={quitando}
        onClose={() => setQuitando(false)}
      />
    </Glass>
  );
}
