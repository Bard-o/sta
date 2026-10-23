import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { ApiError, type Schemas } from "@/api/client";
import {
  DESACTIVACION_KEY,
  useDesactivarCuenta,
  useEstadoDesactivacion,
} from "@/auth/desactivacion";
import { SESION_KEY } from "@/auth/sesion";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogNotice,
  DialogTitle,
} from "@/components/ui/dialog";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { fecha, ZONA_COLOMBIA } from "@/lib/format";

type Bloqueo = Schemas["BloqueoDesactivacion"];

function descripcion(b: Bloqueo) {
  const que = b.tipo === "compra" ? `Compra ${b.codigo_reserva ?? ""}`.trim() : "Reserva";
  return `${que}: vuelo ${b.vuelo_codigo}, ${b.origen} → ${b.destino}, sale el ${fecha(b.salida, ZONA_COLOMBIA)}.`;
}

/** S05 · Desactivar cuenta (HU-09). Solo el cliente. Es un borrado lógico: se conservan los datos,
 *  el histórico y el saldo, pero no se puede volver a iniciar sesión. Con compras o reservas
 *  activas en vuelos futuros el botón queda deshabilitado y se listan cuáles. */
export function DesactivarCuenta() {
  const estado = useEstadoDesactivacion();
  const desactivar = useDesactivarCuenta();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [abierto, setAbierto] = useState(false);

  const confirmar = () =>
    desactivar.mutate(undefined, {
      onSuccess: () => {
        // Primero se sale de la pantalla protegida; luego se olvida la sesión (ya la cerró el servidor).
        navigate("/", { replace: true });
        queryClient.clear();
        queryClient.setQueryData(SESION_KEY, null);
        toast("Desactivamos tu cuenta. Ya no podrás iniciar sesión.");
      },
      onError: (error) => {
        // Entre tanto pudo aparecer una compra activa: se cierra el diálogo y se muestra cuál.
        if (error instanceof ApiError && error.codigo === "tiquetes_activos") {
          setAbierto(false);
          void queryClient.invalidateQueries({ queryKey: DESACTIVACION_KEY });
        }
      },
    });

  const bloqueos = estado.data?.bloqueos ?? [];
  const puede = estado.data?.puede_desactivar === true;
  const error = desactivar.error;
  const errorGeneral = error && !(error instanceof ApiError && error.codigo === "tiquetes_activos");

  return (
    <Glass as="div" title="Desactivar cuenta">
      <p className="mb-3">
        Conservamos tu histórico y tu saldo, pero no podrás volver a iniciar sesión.
      </p>

      {estado.isError && <Notice tone="danger">{estado.error.message}</Notice>}
      {error instanceof ApiError && error.codigo === "tiquetes_activos" && (
        <Notice tone="danger">{error.message}</Notice>
      )}
      {bloqueos.length > 0 && (
        <Notice tone="danger">
          Para desactivar tu cuenta, cancela estas compras o reservas, o espera a que se realicen:
          <ul className="mt-2 list-disc pl-5">
            {bloqueos.map((b) => (
              <li key={`${b.tipo}-${b.codigo_reserva ?? b.vuelo_id}`}>{descripcion(b)}</li>
            ))}
          </ul>
        </Notice>
      )}

      <Dialog open={abierto} onOpenChange={setAbierto}>
        <Button variant="danger" disabled={!puede} onClick={() => setAbierto(true)}>
          Desactivar cuenta
        </Button>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Desactivar tu cuenta?</DialogTitle>
            <DialogDescription>
              Es el último paso: se cerrará tu sesión en todos tus dispositivos.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <DialogNotice>
              No podrás volver a iniciar sesión con esta cuenta. Conservamos tus datos, tu histórico
              y el saldo de tu monedero.
            </DialogNotice>
            {errorGeneral && <Notice tone="danger">{error.message}</Notice>}
          </DialogBody>
          <DialogFooter>
            <Button variant="danger" onClick={confirmar} disabled={desactivar.isPending}>
              {desactivar.isPending ? "Desactivando…" : "Desactivar cuenta"}
            </Button>
            <DialogClose asChild>
              <Button variant="secondary">Volver</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Glass>
  );
}
