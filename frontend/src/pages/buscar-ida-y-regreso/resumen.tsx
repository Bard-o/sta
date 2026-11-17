import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useAgregarSeleccion } from "@/auth/carrito";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { cop } from "@/lib/format";
import type { VueloBusqueda } from "../buscar/api";
import { NOMBRE_CLASE, type Clase } from "./esquema";

export type Perfil = "cliente" | "visitante" | "personal";

/** «Trayecto completo, 2 viajeros»: el total es la suma de los precios vigentes de ambos vuelos
 *  por los viajeros, sin descuento combinado (RF-40); se agrega al carrito como una sola
 *  selección de dos tramos (HU-26). */
export function ResumenTrayecto({
  ida,
  claseIda,
  regreso,
  claseRegreso,
  viajeros,
  perfil,
  rutaLogin,
}: {
  ida: VueloBusqueda;
  claseIda: Clase;
  regreso: VueloBusqueda;
  claseRegreso: Clase;
  viajeros: number;
  perfil: Perfil;
  rutaLogin: string;
}) {
  const navigate = useNavigate();
  const agregar = useAgregarSeleccion();
  const total = (ida[claseIda].precio_vigente + regreso[claseRegreso].precio_vigente) * viajeros;

  function agregarAlCarrito() {
    agregar.mutate(
      {
        tramos: [
          { vuelo_id: ida.id, clase: claseIda },
          { vuelo_id: regreso.id, clase: claseRegreso },
        ],
        viajeros,
      },
      {
        onSuccess: () =>
          toast.success(`Agregamos ${ida.codigo} y ${regreso.codigo} al carrito.`, {
            action: { label: "Ver carrito", onClick: () => void navigate("/carrito") },
          }),
      },
    );
  }

  return (
    <Glass variant="strong" aria-label="Trayecto completo">
      <div className="sta-between">
        <div>
          <h2 className="sta-panel-title">
            Trayecto completo, {viajeros} {viajeros === 1 ? "viajero" : "viajeros"}
          </h2>
          <p className="caption sta-muted">
            Ida en {NOMBRE_CLASE[claseIda]} y regreso en {NOMBRE_CLASE[claseRegreso]}. Quedan
            vinculados bajo un mismo código.
          </p>
        </div>
        <p className="price" aria-label={`Total ${cop(total)}`}>
          {cop(total)}
        </p>
        {perfil === "cliente" && (
          <Button variant="primary" disabled={agregar.isPending} onClick={agregarAlCarrito}>
            {agregar.isPending ? "Agregando…" : "Agregar al carrito"}
          </Button>
        )}
        {perfil === "visitante" && (
          <Button variant="primary" href={`/login?next=${encodeURIComponent(rutaLogin)}`}>
            Inicia sesión para agregar
          </Button>
        )}
      </div>
      {agregar.isError && (
        <div className="mt-3">
          <Notice tone="danger">{agregar.error.message}</Notice>
        </div>
      )}
    </Glass>
  );
}
