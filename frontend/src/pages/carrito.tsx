import { useState } from "react";
import { useCarrito } from "@/auth/carrito";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { cop } from "@/lib/format";
import { VaciarCarritoDialogo } from "./carrito/vaciar-dialogo";
import { SeleccionCard } from "./carrito/seleccion";

/** S16 Carrito (HU-22, HU-23). Cada selección se confirma por separado: «Continuar» lleva a los
 *  datos de los viajeros de esa selección (S17, #128). */
export function CarritoPage() {
  const { data: carrito, isPending, isError, error, refetch } = useCarrito();
  const [vaciando, setVaciando] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <div className="sta-between">
        <div>
          <h1 className="sta-h1">Tu carrito</h1>
          <p className="sta-sub">
            Las sillas no se bloquean aquí: se bloquean al iniciar la compra. Los precios se
            actualizan cada vez que abres el carrito.
          </p>
        </div>
        {carrito && carrito.cantidad > 0 && (
          <Button variant="danger" icon="x" onClick={() => setVaciando(true)}>
            Vaciar carrito
          </Button>
        )}
      </div>

      {isPending && <p className="body sta-muted">Cargando tu carrito…</p>}

      {isError && (
        <Notice tone="danger">
          <div className="flex flex-col items-start gap-2">
            <span>{error.message}</span>
            <Button size="sm" onClick={() => void refetch()}>
              Reintentar
            </Button>
          </div>
        </Notice>
      )}

      {carrito && carrito.cantidad === 0 && (
        <Glass title="Tu carrito está vacío">
          <div className="flex flex-col items-start gap-4">
            <p className="body sta-muted">
              Busca un vuelo y agrégalo para reservarlo o comprarlo desde aquí.
            </p>
            <Button variant="primary" icon="search" href="/buscar">
              Buscar vuelos
            </Button>
          </div>
        </Glass>
      )}

      {carrito && carrito.cantidad > 0 && (
        <>
          {carrito.selecciones.map((seleccion) => (
            <SeleccionCard key={seleccion.id} seleccion={seleccion} />
          ))}
          <Glass variant="inset">
            <p className="overline sta-muted">TOTAL DE LAS SELECCIONES DISPONIBLES</p>
            <p className="price">{cop(carrito.total)}</p>
            <p className="caption sta-muted">
              Cada selección se reserva o se paga por separado. No suma las que no se pueden
              confirmar.
            </p>
          </Glass>
        </>
      )}

      <VaciarCarritoDialogo
        abierto={vaciando}
        cantidad={carrito?.cantidad ?? 0}
        onClose={() => setVaciando(false)}
      />
    </div>
  );
}
