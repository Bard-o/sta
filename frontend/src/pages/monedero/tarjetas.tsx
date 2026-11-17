import { useState } from "react";
import { toast } from "sonner";
import type { Schemas } from "@/api/client";
import { useEliminarTarjeta, useTarjetas } from "@/auth/monedero";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogNotice,
  DialogTitle,
} from "@/components/ui/dialog";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { NOMBRE_FRANQUICIA, NOMBRE_TIPO } from "@/lib/tarjeta";

type Tarjeta = Schemas["Tarjeta"];

/** «Crédito, Visa, Vence 08/28»: lo que se sabe de la tarjeta sin mostrar su número (RF-46). */
const descripcion = (t: Tarjeta) =>
  `${NOMBRE_TIPO[t.tipo]}, ${NOMBRE_FRANQUICIA[t.franquicia]}, Vence ${t.vencimiento}`;

/** Confirmación de HU-29: eliminar una tarjeta no se puede deshacer, pero no toca el historial. */
function EliminarDialogo({ tarjeta, onClose }: { tarjeta: Tarjeta; onClose: () => void }) {
  const eliminar = useEliminarTarjeta();

  function confirmar() {
    eliminar.mutate(tarjeta.id, {
      onSuccess: () => {
        toast.success(`Eliminamos la tarjeta ${tarjeta.numero_enmascarado}.`);
        onClose();
      },
    });
  }

  return (
    <Dialog open onOpenChange={(abierto) => !abierto && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Eliminar la tarjeta {tarjeta.numero_enmascarado}?</DialogTitle>
          <DialogDescription>{descripcion(tarjeta)}.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <DialogNotice tone="info">
            Dejará de servir para recargar. Las recargas que ya hiciste con ella siguen en tus
            movimientos con su referencia.
          </DialogNotice>
          {eliminar.isError && <Notice tone="danger">{eliminar.error.message}</Notice>}
        </DialogBody>
        <DialogFooter>
          <Button variant="danger" disabled={eliminar.isPending} onClick={confirmar}>
            {eliminar.isPending ? "Eliminando…" : "Eliminar tarjeta"}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Volver
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** «Tus tarjetas» (HU-29): enmascaradas, con su franquicia y su vencimiento; las vencidas se
 *  marcan con palabras y también se pueden eliminar. */
export function PanelTarjetas() {
  const tarjetas = useTarjetas();
  const [aEliminar, setAEliminar] = useState<Tarjeta | null>(null);

  return (
    <Glass
      title="Tus tarjetas"
      actions={
        <Button variant="ghost" size="sm" href="/monedero/tarjetas/nueva">
          Registrar tarjeta
        </Button>
      }
    >
      {tarjetas.isPending && <p className="body sta-muted">Cargando tus tarjetas…</p>}
      {tarjetas.isError && <Notice tone="danger">{tarjetas.error.message}</Notice>}
      {tarjetas.data && tarjetas.data.length === 0 && (
        <p className="body sta-muted">
          No tienes tarjetas registradas. Registra una para recargar tu monedero.
        </p>
      )}
      {tarjetas.data && tarjetas.data.length > 0 && (
        <ul className="flex flex-col divide-y divide-line">
          {tarjetas.data.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-3">
              <div className="flex flex-col gap-1">
                <span className="code">{t.numero_enmascarado}</span>
                <span className="caption sta-muted">{descripcion(t)}</span>
                {t.vencida && (
                  <span>
                    <Badge tone="danger" icon="alert">
                      Vencida
                    </Badge>
                  </span>
                )}
              </div>
              <Button size="sm" onClick={() => setAEliminar(t)}>
                Eliminar <span className="sr-only">la tarjeta {t.numero_enmascarado}</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
      {aEliminar && <EliminarDialogo tarjeta={aEliminar} onClose={() => setAEliminar(null)} />}
    </Glass>
  );
}
