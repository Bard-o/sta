import { toast } from "sonner";
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
import { Notice } from "@/components/ui/notice";
import { fechaHora } from "@/lib/format";
import { useCancelarVuelo, type VueloAdmin } from "./api";

/** Confirmación de HU-16: dice cuántas reservas activas se anularán antes de cancelar. */
export function CancelarVueloDialogo({
  vuelo,
  onClose,
}: {
  vuelo: VueloAdmin | null;
  onClose: () => void;
}) {
  const cancelar = useCancelarVuelo();

  function cerrar() {
    cancelar.reset();
    onClose();
  }

  function confirmar() {
    if (!vuelo) return;
    cancelar.mutate(vuelo.id, {
      onSuccess: ({ reservas_anuladas }) => {
        toast.success(
          reservas_anuladas > 0
            ? `Cancelamos el vuelo ${vuelo.codigo} y anulamos ${reservas_anuladas} ${
                reservas_anuladas === 1 ? "reserva" : "reservas"
              }.`
            : `Cancelamos el vuelo ${vuelo.codigo}.`,
        );
        cerrar();
      },
    });
  }

  return (
    <Dialog open={vuelo !== null} onOpenChange={(abierto) => !abierto && cerrar()}>
      <DialogContent>
        {vuelo && (
          <>
            <DialogHeader>
              <DialogTitle>¿Cancelar el vuelo {vuelo.codigo}?</DialogTitle>
              <DialogDescription>
                {vuelo.origen.nombre} → {vuelo.destino.nombre},{" "}
                {fechaHora(vuelo.salida, vuelo.origen.zona_horaria)}.
              </DialogDescription>
            </DialogHeader>
            <DialogBody>
              {vuelo.reservas_activas > 0 ? (
                <DialogNotice tone="info">
                  Tiene{" "}
                  <strong>
                    {vuelo.reservas_activas}{" "}
                    {vuelo.reservas_activas === 1 ? "reserva activa" : "reservas activas"}
                  </strong>
                  . Se anularán, sus sillas se liberarán y avisaremos a los clientes por correo.
                </DialogNotice>
              ) : (
                <DialogNotice tone="info">No tiene reservas activas.</DialogNotice>
              )}
              <p className="caption sta-muted">
                El vuelo saldrá de la búsqueda y del carrusel. Su código no se vuelve a usar.
              </p>
              {cancelar.isError && <Notice tone="danger">{cancelar.error.message}</Notice>}
            </DialogBody>
            <DialogFooter>
              <Button variant="danger" onClick={confirmar} disabled={cancelar.isPending}>
                {cancelar.isPending ? "Cancelando…" : "Cancelar vuelo"}
              </Button>
              <Button variant="secondary" onClick={cerrar}>
                Volver
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
