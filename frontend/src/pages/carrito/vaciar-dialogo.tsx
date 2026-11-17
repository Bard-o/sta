import { toast } from "sonner";
import { useVaciarCarrito } from "@/auth/carrito";
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

/** Confirmación de HU-23: vaciar el carrito no se puede deshacer. */
export function VaciarCarritoDialogo({
  abierto,
  cantidad,
  onClose,
}: {
  abierto: boolean;
  cantidad: number;
  onClose: () => void;
}) {
  const vaciar = useVaciarCarrito();

  function cerrar() {
    vaciar.reset();
    onClose();
  }

  function confirmar() {
    vaciar.mutate(undefined, {
      onSuccess: () => {
        toast.success("Vaciamos tu carrito.");
        cerrar();
      },
    });
  }

  return (
    <Dialog open={abierto} onOpenChange={(estaAbierto) => !estaAbierto && cerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Vaciar el carrito?</DialogTitle>
          <DialogDescription>
            {cantidad === 1 ? "Hay 1 selección" : `Hay ${cantidad} selecciones`} en tu carrito.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <DialogNotice tone="info">
            Se quitarán todas las selecciones. En el carrito no hay sillas bloqueadas, así que no se
            libera nada. Para volver a verlas tendrás que buscarlas de nuevo.
          </DialogNotice>
          {vaciar.isError && <Notice tone="danger">{vaciar.error.message}</Notice>}
        </DialogBody>
        <DialogFooter>
          <Button variant="danger" onClick={confirmar} disabled={vaciar.isPending}>
            {vaciar.isPending ? "Vaciando…" : "Vaciar carrito"}
          </Button>
          <Button variant="secondary" onClick={cerrar}>
            Volver
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
