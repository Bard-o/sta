import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useAgregarSeleccion } from "@/auth/carrito";
import { Button } from "@/components/ui/button";
import { FlightPass } from "@/components/ui/flight-pass";
import { Notice } from "@/components/ui/notice";
import { cop } from "@/lib/format";
import { AgregarAlCarritoDialogo } from "./agregar-dialogo";
import type { VueloBusqueda } from "./api";
import { NOMBRE_CLASE, type Clase } from "./filtros";
import { datosDelPase } from "./pase";

/** Quién ve el resultado: el cliente agrega, el visitante inicia sesión para agregar y el
 *  administrador y el root solo consultan (no compran, Apéndice B). */
export type Perfil = "cliente" | "visitante" | "personal";

const TITULO: Record<Clase, string> = { economica: "Económica", primera: "Primera clase" };

const lineaDeClase = (vuelo: VueloBusqueda, clase: Clase) =>
  `${TITULO[clase]} ${cop(vuelo[clase].precio_vigente)}: ${
    vuelo[clase].agotada ? "agotada" : `quedan ${vuelo[clase].disponibles}`
  }`;

/** Un resultado de la búsqueda como pasabordo (HU-20): ruta, horas locales, duración, precio
 *  vigente con su promoción, disponibilidad por clase y el botón Agregar (HU-22). */
export function ResultadoVuelo({
  vuelo,
  clase,
  perfil,
  enCarrito,
  rutaLogin,
}: {
  vuelo: VueloBusqueda;
  /** La clase que filtra la búsqueda: define el precio que se muestra. */
  clase: Clase | undefined;
  perfil: Perfil;
  enCarrito: boolean;
  /** A dónde vuelve el visitante después de iniciar sesión. */
  rutaLogin: string;
}) {
  const navigate = useNavigate();
  const agregar = useAgregarSeleccion();
  const [eligiendo, setEligiendo] = useState(false);

  // Sin filtro de clase se muestra económica, salvo que esté agotada y primera no (SUP-20).
  const mostrada: Clase =
    clase ?? (vuelo.economica.agotada && !vuelo.primera.agotada ? "primera" : "economica");
  const datos = vuelo[mostrada];
  const agotado = vuelo.agotado || (clase !== undefined && vuelo[clase].agotada);

  const badges: {
    tone: "accent" | "danger" | "success";
    icon: "tag" | "x" | "check";
    label: string;
  }[] = [];
  if (agotado) {
    badges.push({
      tone: "danger",
      icon: "x",
      label: vuelo.agotado ? "Agotado" : `Agotado en ${NOMBRE_CLASE[clase!]}`,
    });
  }
  for (const c of ["economica", "primera"] as const) {
    const promocion = vuelo[c].promocion;
    if (promocion) {
      badges.push({
        tone: "accent",
        icon: "tag",
        label: `Promoción ${promocion.porcentaje} % en ${NOMBRE_CLASE[c]}`,
      });
    }
  }
  if (enCarrito) badges.push({ tone: "success", icon: "check", label: "En tu carrito" });

  function confirmar(claseElegida: Clase, viajeros: number) {
    agregar.mutate(
      { tramos: [{ vuelo_id: vuelo.id, clase: claseElegida }], viajeros },
      {
        onSuccess: () => {
          setEligiendo(false);
          toast.success(`Agregamos ${vuelo.codigo} al carrito.`, {
            action: { label: "Ver carrito", onClick: () => void navigate("/carrito") },
          });
        },
        // El error se muestra en el resultado, no en el diálogo: el cliente ve cuál falló.
        onError: () => setEligiendo(false),
      },
    );
  }

  const accion = agotado ? (
    <Button size="sm" disabled>
      Agotado
    </Button>
  ) : perfil === "cliente" ? (
    <Button variant="primary" size="sm" onClick={() => setEligiendo(true)}>
      Agregar <span className="sr-only">{vuelo.codigo} al carrito</span>
    </Button>
  ) : perfil === "visitante" ? (
    <Button variant="primary" size="sm" href={`/login?next=${encodeURIComponent(rutaLogin)}`}>
      Agregar <span className="sr-only">{vuelo.codigo} al carrito (inicia sesión)</span>
    </Button>
  ) : undefined;

  return (
    <div className="flex flex-col gap-2">
      <FlightPass
        {...datosDelPase(vuelo)}
        badges={badges}
        note={`${lineaDeClase(vuelo, "economica")} · ${lineaDeClase(vuelo, "primera")}`}
        oldPrice={datos.promocion ? cop(datos.precio_base) : undefined}
        price={cop(datos.precio_vigente)}
        priceNote={`${TITULO[mostrada]} · por viajero`}
        state={agotado ? "soldout" : enCarrito ? "selected" : "default"}
        action={accion}
      />
      {agregar.isError && <Notice tone="danger">{agregar.error.message}</Notice>}
      {eligiendo && (
        <AgregarAlCarritoDialogo
          vuelo={vuelo}
          claseInicial={
            datos.agotada ? (mostrada === "economica" ? "primera" : "economica") : mostrada
          }
          enviando={agregar.isPending}
          onConfirmar={confirmar}
          onClose={() => setEligiendo(false)}
        />
      )}
    </div>
  );
}
