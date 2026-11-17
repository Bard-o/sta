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

/** Cancelar la compra suelta las sillas bloqueadas (HU-25): se confirma antes (IU-07). */
export function CancelarCompraDialogo({
  codigo,
  enviando,
  error,
  onConfirmar,
  onClose,
}: {
  codigo: string;
  enviando: boolean;
  error: string | null;
  onConfirmar: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open onOpenChange={(abierto) => !abierto && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Cancelar la compra {codigo}?</DialogTitle>
          <DialogDescription>No se cobra nada.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <DialogNotice tone="info">
            Se liberan las sillas bloqueadas y vuelves al carrito, donde sigue tu selección.
          </DialogNotice>
          {error && <Notice tone="danger">{error}</Notice>}
        </DialogBody>
        <DialogFooter>
          <Button variant="danger" disabled={enviando} onClick={onConfirmar}>
            {enviando ? "Cancelando…" : "Cancelar compra"}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Volver
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
