import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch, type FieldPath } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { useCarrito, useQuitarSeleccion, type SeleccionCarrito } from "@/auth/carrito";
import { usePerfil } from "@/auth/perfil";
import { esCorreoNoVerificado, useIrAVerificacion } from "@/auth/verificacion";
import { useIniciarCompra, useReservar, type ViajeEntrada } from "@/auth/viajes";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { Pasos } from "@/components/ui/pasos";
import { cop, fecha, fechaHora, hora, ZONA_COLOMBIA } from "@/lib/format";
import { edadEn, MAYORIA_DE_EDAD } from "@/lib/persona";
import {
  esquema,
  viajeroVacio,
  type Clase,
  type Datos,
  type Entrada,
} from "./compra-viajeros/esquema";
import { TarjetaViajero } from "./compra-viajeros/tarjeta-viajero";
import { useVueloDetalle } from "./noticias-comunes/api";

type Modo = "reservar" | "comprar";

const PASOS = ["Vuelos", "Viajeros", "Pago"];

/** Fecha local de la salida (aaaa-mm-dd) en la zona del origen: con ella se calcula la edad. */
const fechaLocalIso = (iso: string, zona: string) =>
  new Date(iso).toLocaleDateString("sv-SE", { timeZone: zona });

/** S17 Datos de viajeros y elección entre reservar o comprar (HU-24, HU-25, HU-26). La selección
 *  llega del carrito (`?seleccion=<id>`). Reservar crea la reserva y vuelve a Mis viajes; comprar
 *  inicia la compra (bloquea las sillas) y sigue al pago (S18, #134). Sin el correo verificado lleva a
 *  la verificación (HU-02). */
export function CompraViajerosPage() {
  const [params] = useSearchParams();
  const seleccionId = Number(params.get("seleccion"));
  const carrito = useCarrito();
  const seleccion = carrito.data?.selecciones.find((s) => s.id === seleccionId);

  if (!Number.isInteger(seleccionId) || seleccionId < 1 || (carrito.data && !seleccion)) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        <h1 className="sta-h1">¿Quiénes viajan?</h1>
        <Notice tone="info">
          Esa selección ya no está en tu carrito: pudo reservarse, comprarse o quitarse.
        </Notice>
        <div>
          <Button variant="primary" href="/carrito">
            Volver al carrito
          </Button>
        </div>
      </div>
    );
  }
  if (carrito.isError) return <Notice tone="danger">{carrito.error.message}</Notice>;
  if (!seleccion) return <p className="body sta-muted">Cargando tu selección…</p>;
  if (!seleccion.confirmable) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        <h1 className="sta-h1">¿Quiénes viajan?</h1>
        <Notice tone="danger">
          Esta selección ya no se puede reservar ni comprar. Revisa los avisos en tu carrito.
        </Notice>
        <div>
          <Button variant="primary" href="/carrito">
            Volver al carrito
          </Button>
        </div>
      </div>
    );
  }
  return <FormularioViajeros key={seleccion.id} seleccion={seleccion} />;
}

function FormularioViajeros({ seleccion }: { seleccion: SeleccionCarrito }) {
  const navigate = useNavigate();
  const irAVerificacion = useIrAVerificacion();
  const reservar = useReservar();
  const comprar = useIniciarCompra();
  const quitar = useQuitarSeleccion();
  const { data: perfil } = usePerfil();
  const [modo, setModo] = useState<Modo>("reservar");
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null);

  const tramos = seleccion.tramos;
  const vuelo0 = useVueloDetalle(tramos[0].vuelo.id);
  const vuelo1 = useVueloDetalle(tramos[1]?.vuelo.id ?? 0);
  const vuelos = [vuelo0.data, tramos[1] ? vuelo1.data : undefined].slice(0, tramos.length);
  const fechasDeSalida = tramos.map((t) =>
    fechaLocalIso(t.vuelo.salida, t.vuelo.origen.zona_horaria),
  );

  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: {
      viajeros: Array.from({ length: seleccion.viajeros }, () =>
        viajeroVacio(tramos.map((t) => t.clase)),
      ),
    },
  });
  const viajeros = useWatch({ control: form.control, name: "viajeros" });

  // Precio de cada tramo con la clase elegida: el del vuelo de hoy, o el de la selección si es
  // la misma clase y el detalle del vuelo todavía no llegó.
  const precioDe = (tramo: number, clase: Clase) =>
    vuelos[tramo]?.[clase].precio_vigente ??
    (tramos[tramo].clase === clase ? tramos[tramo].precio_unitario : null);
  const precios = viajeros.flatMap((v) => v.clases.map((c, t) => precioDe(t, c as Clase)));
  const total = precios.includes(null) ? null : precios.reduce<number>((s, p) => s + (p ?? 0), 0);

  // HU-24: si ningún viajero será mayor de edad el día de algún vuelo, se advierte antes de enviar.
  const sinAdulto = fechasDeSalida.some((dia) => {
    const fechas = viajeros.map((v) => v.fecha_nacimiento);
    if (fechas.some((f) => !/^\d{4}-\d{2}-\d{2}$/.test(f))) return false;
    return !fechas.some((f) => edadEn(f, dia) >= MAYORIA_DE_EDAD);
  });

  const cantidadTiquetes = seleccion.viajeros * tramos.length;
  const ida = tramos[0].vuelo;
  const ruta = [ida.origen.nombre, ...tramos.map((t) => t.vuelo.destino.nombre)].join(" → ");
  const codigos = tramos.map((t) => t.vuelo.codigo).join(" y ");

  function aplicarError(error: unknown) {
    setErrorGeneral(null);
    // HU-02: sin el correo verificado va a la verificación; la selección sigue en el carrito.
    if (esCorreoNoVerificado(error)) {
      irAVerificacion(`/compra/viajeros?seleccion=${seleccion.id}`);
      return;
    }
    if (!(error instanceof ApiError)) {
      setErrorGeneral("No pudimos completar la solicitud. Intenta de nuevo.");
      return;
    }
    for (const [campo, mensaje] of Object.entries(error.campos)) {
      if (campo.startsWith("viajeros.")) {
        form.setError(campo as FieldPath<Entrada>, { message: mensaje });
      }
    }
    // Un error con campo del viajero se pinta junto al campo y, además, el resumen arriba;
    // los demás (cupo, límite, vuelo cerrado) solo tienen el aviso general.
    setErrorGeneral(error.message);
  }

  const enviar = form.handleSubmit((datos) => {
    setErrorGeneral(null);
    const cuerpo: ViajeEntrada = {
      tramos: tramos.map((t) => ({ vuelo_id: t.vuelo.id })),
      viajeros: datos.viajeros.map((v) => ({
        ...v,
        tipo_documento: v.tipo_documento as ViajeEntrada["viajeros"][number]["tipo_documento"],
        genero: v.genero as ViajeEntrada["viajeros"][number]["genero"],
        clases: v.clases,
      })),
    };
    if (modo === "reservar") {
      reservar.mutate(cuerpo, {
        onSuccess: (viaje) => {
          toast.success(`Reservamos tus tiquetes. Tu código de reserva es ${viaje.codigo}.`);
          void navigate("/mis-viajes?tipo=reserva");
          // La selección ya se convirtió en reserva: sale del carrito.
          quitar.mutate(seleccion.id);
        },
        onError: aplicarError,
      });
    } else {
      comprar.mutate(cuerpo, {
        onSuccess: (compra) => {
          void navigate(`/compra/pago/${compra.id}?seleccion=${seleccion.id}`);
        },
        onError: aplicarError,
      });
    }
  });

  const enviando = reservar.isPending || comprar.isPending;
  const verbo = modo === "reservar" ? "Reservar" : "Comprar";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <Pasos pasos={PASOS} actual={1} />
      <div>
        <h1 className="sta-h1">¿Quiénes viajan?</h1>
        <p className="sta-sub">
          {codigos}, {ruta}, {fechaHora(ida.salida, ida.origen.zona_horaria)} (hora local). La edad
          se calcula a la fecha del vuelo.
        </p>
      </div>

      <Form {...form}>
        <form onSubmit={enviar} noValidate className="flex flex-col gap-6 lg:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-4">
            {viajeros.map((_, i) => (
              <TarjetaViajero
                key={i}
                indice={i}
                vuelos={vuelos}
                fechasDeSalida={fechasDeSalida}
                perfil={perfil}
              />
            ))}
          </div>

          <aside className="flex w-full flex-col gap-4 lg:w-80 lg:shrink-0">
            <h2 className="sta-panel-title">¿Reservas o compras?</h2>
            <div
              role="radiogroup"
              aria-label="¿Reservas o compras?"
              className="flex flex-col gap-3"
            >
              <OpcionDeCompra
                seleccionada={modo === "reservar"}
                titulo="Reservar sin pagar"
                onElegir={() => setModo("reservar")}
              >
                Congela el precio y las sillas
                {seleccion.reserva_venceria_en
                  ? ` hasta el ${fecha(seleccion.reserva_venceria_en, ZONA_COLOMBIA)} a las ${hora(seleccion.reserva_venceria_en, ZONA_COLOMBIA)} (hora de Colombia)`
                  : ""}
                . Si no pagas, se libera sola.
              </OpcionDeCompra>
              <OpcionDeCompra
                seleccionada={modo === "comprar"}
                titulo="Comprar ahora"
                onElegir={() => setModo("comprar")}
              >
                Pagas con tu monedero y recibes el código de reserva. Bloqueamos las sillas 15
                minutos mientras pagas.
              </OpcionDeCompra>
            </div>

            <Notice tone="info">
              Asignaremos sillas juntas, en un bloque de la misma fila, elegido al azar. Podrás
              cambiarla una vez antes del check-in.
            </Notice>

            {sinAdulto && (
              <Notice tone="danger">
                Un menor de edad debe viajar con al menos un adulto en el mismo vuelo. Revisa las
                fechas de nacimiento.
              </Notice>
            )}
            {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

            <Glass variant="inset" aria-label="Total">
              <p className="overline sta-muted">TOTAL</p>
              <p className="price">{total === null ? "—" : cop(total)}</p>
              <p className="caption sta-muted">
                {seleccion.viajeros} {seleccion.viajeros === 1 ? "viajero" : "viajeros"}
                {tramos.length === 2 ? ", ida y regreso" : ""}. Sin descuento combinado.
              </p>
            </Glass>

            <Button type="submit" variant="primary" block disabled={enviando}>
              {enviando
                ? "Enviando…"
                : `${verbo} ${cantidadTiquetes} ${cantidadTiquetes === 1 ? "tiquete" : "tiquetes"}`}
            </Button>
            <Button variant="ghost" block href="/carrito">
              Volver al carrito
            </Button>
          </aside>
        </form>
      </Form>
    </div>
  );
}

/** Una de las dos formas de seguir: reservar o comprar. Un radio con título y explicación. */
function OpcionDeCompra({
  seleccionada,
  titulo,
  onElegir,
  children,
}: {
  seleccionada: boolean;
  titulo: string;
  onElegir: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={seleccionada}
      onClick={onElegir}
      className="sta-glass sta-glass--inset sta-glass--pad flex flex-col gap-1 text-left"
      // `.sta-glass` pinta su borde fuera de las capas de Tailwind: el elegido lleva borde de tinta.
      style={seleccionada ? { borderColor: "var(--ink)", borderWidth: "2px" } : undefined}
    >
      <span className="body-strong">{titulo}</span>
      <span className="caption sta-muted">{children}</span>
    </button>
  );
}
