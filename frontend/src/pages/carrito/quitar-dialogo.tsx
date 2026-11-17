import { toast } from "sonner";
import { useQuitarSeleccion, type SeleccionCarrito } from "@/auth/carrito";
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

/** Confirmación de HU-23 al quitar una selección: dice cuál es y que las demás no se tocan. */
export function QuitarSeleccionDialogo({
  seleccion,
  abierto,
  onClose,
}: {
  seleccion: SeleccionCarrito;
  abierto: boolean;
  onClose: () => void;
}) {
  const quitar = useQuitarSeleccion();
  const [ida, regreso] = seleccion.tramos;
  const completo = regreso !== undefined;
  const codigos = seleccion.tramos.map((t) => t.vuelo.codigo).join(" y ");

  function cerrar() {
    quitar.reset();
    onClose();
  }

  function confirmar() {
    quitar.mutate(seleccion.id, {
      onSuccess: () => {
        toast.success(`Quitamos ${codigos} del carrito.`);
        onClose();
      },
    });
  }

  return (
    <Dialog open={abierto} onOpenChange={(estaAbierto) => !estaAbierto && cerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {completo ? "¿Quitar el trayecto completo?" : `¿Quitar el vuelo ${ida.vuelo.codigo}?`}
          </DialogTitle>
          <DialogDescription>
            {completo
              ? `${ida.vuelo.origen.nombre} → ${ida.vuelo.destino.nombre} → ${regreso.vuelo.destino.nombre} (${codigos}).`
              : `${ida.vuelo.origen.nombre} → ${ida.vuelo.destino.nombre}.`}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <DialogNotice tone="info">
            Solo se quita esta selección; las demás siguen en tu carrito. No hay sillas bloqueadas,
            así que no se libera nada. Para recuperarla tendrás que buscarla de nuevo.
          </DialogNotice>
          {quitar.isError && <Notice tone="danger">{quitar.error.message}</Notice>}
        </DialogBody>
        <DialogFooter>
          <Button variant="danger" onClick={confirmar} disabled={quitar.isPending}>
            {quitar.isPending ? "Quitando…" : "Quitar del carrito"}
          </Button>
          <Button variant="secondary" onClick={cerrar}>
            Volver
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
