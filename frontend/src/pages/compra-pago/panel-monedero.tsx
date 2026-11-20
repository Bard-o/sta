import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { cop } from "@/lib/format";

/** Una fila «etiqueta … valor» del panel del monedero. */
function Fila({ etiqueta, valor, fuerte }: { etiqueta: string; valor: string; fuerte?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className={fuerte ? "body-strong" : "body"}>{etiqueta}</dt>
      <dd className={fuerte ? "price" : "body-strong"}>{valor}</dd>
    </div>
  );
}

/** «Tu monedero» (S18): saldo actual, esta compra y saldo después, con el botón de pagar. Con
 *  saldo insuficiente el botón queda deshabilitado y el panel dice cuánto falta (HU-25). */
export function PanelMonedero({
  saldo,
  total,
  pagando,
  error,
  onPagar,
}: {
  saldo: number | undefined;
  total: number;
  pagando: boolean;
  error: string | null;
  onPagar: () => void;
}) {
  const alcanza = saldo !== undefined && saldo >= total;
  return (
    <Glass title="Tu monedero" className="lg:w-96 lg:shrink-0">
      <dl className="flex flex-col gap-3">
        <Fila etiqueta="Saldo actual" valor={saldo === undefined ? "…" : cop(saldo)} />
        <Fila etiqueta="Esta compra" valor={cop(-total)} />
        <hr className="border-line" />
        <Fila
          etiqueta="Saldo después"
          valor={saldo === undefined ? "…" : alcanza ? cop(saldo - total) : "No alcanza"}
          fuerte
        />
      </dl>
      <div className="mt-4 flex flex-col gap-3">
        {error && <Notice tone="danger">{error}</Notice>}
        <Button variant="primary" block disabled={pagando || !alcanza} onClick={onPagar}>
          {pagando ? "Pagando…" : `Pagar ${cop(total)}`}
        </Button>
        <p className="caption sta-muted">
          Al pagar enviamos el código de reserva a cada viajero y el comprobante en PDF a tu correo.
        </p>
      </div>
    </Glass>
  );
}
