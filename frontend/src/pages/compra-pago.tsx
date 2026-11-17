import { useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useQuitarSeleccion } from "@/auth/carrito";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { Pasos } from "@/components/ui/pasos";
import { cop } from "@/lib/format";
import {
  reloj,
  useCompra,
  useConfirmarCompra,
  useSaldo,
  useSegundosRestantes,
  useSoltarCompra,
  type Compra,
} from "./compra-pago/api";
import { CancelarCompraDialogo } from "./compra-pago/cancelar-dialogo";
import { PanelMonedero } from "./compra-pago/panel-monedero";
import { ResumenCompra } from "./compra-pago/resumen-compra";

const PASOS = ["Vuelos", "Viajeros", "Pago"];

/** S18 Pago con monedero (HU-25, HU-26). Confirma la compra que inició S17: el resumen con las
 *  sillas asignadas, el saldo, la cuenta regresiva del bloqueo de 15 minutos y el camino a
 *  recargar si el saldo no alcanza. `?seleccion=<id>` es la selección del carrito de la que
 *  salió la compra: se quita al pagar. */
export function CompraPagoPage() {
  const { compraId } = useParams();
  const id = Number(compraId);
  const compra = useCompra(id);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <Pasos pasos={PASOS} actual={2} />
      {compra.isPending && compra.fetchStatus !== "idle" && (
        <p className="body sta-muted">Cargando tu compra…</p>
      )}
      {(compra.isError || !Number.isInteger(id) || id < 1) && (
        <>
          <h1 className="sta-h1">Paga con tu monedero</h1>
          <Notice tone="danger">
            {compra.error instanceof ApiError && compra.error.status !== 404
              ? compra.error.message
              : "La compra no existe o no es tuya."}
          </Notice>
          <div>
            <Button variant="primary" href="/carrito">
              Volver al carrito
            </Button>
          </div>
        </>
      )}
      {compra.data && <VistaDeCompra compra={compra.data} id={id} />}
    </div>
  );
}

function VistaDeCompra({ compra, id }: { compra: Compra; id: number }) {
  if (compra.estado === "activa") return <CompraPagada compra={compra} />;
  if (compra.estado !== "pendiente") return <SillasLiberadas />;
  return <PagoPendiente compra={compra} id={id} />;
}

/** El bloqueo de 15 minutos venció o la compra se soltó: las sillas se liberaron, sin cobro. */
function SillasLiberadas() {
  return (
    <>
      <h1 className="sta-h1">Paga con tu monedero</h1>
      <Notice tone="danger">
        Las sillas se liberaron porque pasaron 15 minutos sin confirmar. No te cobramos nada. Vuelve
        a empezar la compra.
      </Notice>
      <div>
        <Button variant="primary" href="/carrito">
          Empezar de nuevo
        </Button>
      </div>
    </>
  );
}

/** Compra pagada: el código de reserva y el aviso de lo que llegó por correo (RF-39). */
function CompraPagada({ compra }: { compra: Compra }) {
  return (
    <>
      <h1 className="sta-h1">Compra pagada</h1>
      <Glass title="Tu código de reserva">
        <p className="display-xl" aria-label={`Código de reserva ${compra.codigo}`}>
          {compra.codigo}
        </p>
        <p className="body sta-muted">
          Enviamos el código de reserva a cada viajero y el comprobante en PDF a tu correo. Con el
          código puedes hacer el check-in.
        </p>
      </Glass>
      <ResumenCompra compra={compra} />
      <div className="flex flex-wrap gap-3">
        <Button variant="primary" href="/mis-viajes?tipo=compra">
          Ver mis viajes
        </Button>
        <Button href="/buscar">Seguir buscando vuelos</Button>
      </div>
    </>
  );
}

function PagoPendiente({ compra, id }: { compra: Compra; id: number }) {
  const navigate = useNavigate();
  const ubicacion = useLocation();
  const [params] = useSearchParams();
  const seleccion = Number(params.get("seleccion"));
  const saldo = useSaldo();
  const confirmar = useConfirmarCompra(id);
  const soltar = useSoltarCompra(id);
  const quitar = useQuitarSeleccion();
  const [cancelando, setCancelando] = useState(false);
  const [vencidaEnServidor, setVencidaEnServidor] = useState(false);
  const restantes = useSegundosRestantes(compra.vence_en);

  const faltante = saldo.data ? Math.max(0, compra.total_pendiente - saldo.data.saldo) : 0;
  const volver = ubicacion.pathname + ubicacion.search;
  const urlRecarga = `/monedero/recargar?faltante=${faltante}&codigo=${encodeURIComponent(compra.codigo)}&volver=${encodeURIComponent(volver)}`;

  if (vencidaEnServidor || restantes === 0) return <SillasLiberadas />;

  const errorDePago = confirmar.error;
  const sinVerificar =
    errorDePago instanceof ApiError && errorDePago.codigo === "correo_no_verificado";
  const mensajeDeError =
    errorDePago &&
    !sinVerificar &&
    !(errorDePago instanceof ApiError && errorDePago.codigo === "bloqueo_vencido")
      ? errorDePago.message
      : null;

  function pagar() {
    confirmar.mutate(undefined, {
      onSuccess: () => {
        // La compra ya está pagada: la selección sale del carrito.
        if (Number.isInteger(seleccion) && seleccion > 0) quitar.mutate(seleccion);
      },
      onError: (error) => {
        if (error instanceof ApiError && error.codigo === "bloqueo_vencido") {
          setVencidaEnServidor(true);
        }
      },
    });
  }

  function cancelarCompra() {
    soltar.mutate(undefined, { onSuccess: () => void navigate("/carrito") });
  }

  return (
    <>
      <h1 className="sta-h1">Paga con tu monedero</h1>
      <Notice tone="info">
        <span role="timer">
          <strong>
            Sillas bloqueadas por {restantes === null ? "—" : reloj(restantes)} minutos.
          </strong>{" "}
          Si no confirmas, se liberan para otros clientes.
        </span>
      </Notice>

      <div className="flex flex-col gap-6 lg:flex-row">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <ResumenCompra compra={compra} />
          {faltante > 0 && (
            <Glass title="Si el saldo no alcanza">
              <div className="flex flex-col items-start gap-3">
                <Notice tone="danger">
                  Te faltan {cop(faltante)}. Recarga tu monedero y vuelve a esta compra sin perder
                  tus sillas.
                </Notice>
                <Button href={urlRecarga}>Recargar {cop(faltante)}</Button>
              </div>
            </Glass>
          )}
          <div>
            <Button variant="ghost" onClick={() => setCancelando(true)}>
              Cancelar compra
            </Button>
          </div>
        </div>
        <PanelMonedero
          saldo={saldo.data?.saldo}
          total={compra.total_pendiente}
          pagando={confirmar.isPending}
          sinVerificar={sinVerificar}
          error={mensajeDeError}
          onPagar={pagar}
        />
      </div>

      {cancelando && (
        <CancelarCompraDialogo
          codigo={compra.codigo}
          enviando={soltar.isPending}
          error={soltar.error?.message ?? null}
          onConfirmar={cancelarCompra}
          onClose={() => setCancelando(false)}
        />
      )}
    </>
  );
}
