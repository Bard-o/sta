import { useState } from "react";
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
import { Field } from "@/components/ui/field";
import { cop, fecha } from "@/lib/format";
import type { VueloBusqueda } from "./api";
import { NOMBRE_CLASE, type Clase } from "./filtros";

/** Máximo de tiquetes activos por cliente en un vuelo (RF-32); el servidor lo vuelve a validar. */
const CANTIDADES = ["1", "2", "3", "4", "5"];

/** HU-22: elegir la clase y la cantidad de viajeros antes de agregar el vuelo al carrito. No
 *  bloquea sillas: eso ocurre al iniciar la compra. */
export function AgregarAlCarritoDialogo({
  vuelo,
  claseInicial,
  enviando,
  onConfirmar,
  onClose,
}: {
  vuelo: VueloBusqueda;
  claseInicial: Clase;
  enviando: boolean;
  onConfirmar: (clase: Clase, viajeros: number) => void;
  onClose: () => void;
}) {
  const [clase, setClase] = useState<Clase>(claseInicial);
  const [viajeros, setViajeros] = useState("1");
  const datos = vuelo[clase];
  const etiqueta = (c: Clase) =>
    `${c === "economica" ? "Económica" : "Primera clase"}, ${cop(vuelo[c].precio_vigente)}${
      vuelo[c].agotada ? " (agotada)" : ""
    }`;

  return (
    <Dialog open onOpenChange={(abierto) => !abierto && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Agregar {vuelo.codigo} al carrito</DialogTitle>
          <DialogDescription>
            {vuelo.origen.nombre} → {vuelo.destino.nombre}, salida{" "}
            {fecha(vuelo.salida, vuelo.origen.zona_horaria)}.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <div className="flex flex-col gap-3">
            <Field
              label="Clase"
              options={(["economica", "primera"] as const).map((c) => ({
                value: c,
                label: etiqueta(c),
              }))}
              value={clase}
              onChange={(e) => setClase(e.target.value as Clase)}
              error={datos.agotada ? "Esta clase no tiene sillas disponibles." : undefined}
            />
            <Field
              label="Viajeros"
              options={CANTIDADES}
              value={viajeros}
              onChange={(e) => setViajeros(e.target.value)}
            />
            <DialogNotice tone="info">
              Total estimado: <strong>{cop(datos.precio_vigente * Number(viajeros))}</strong> por{" "}
              {viajeros} {viajeros === "1" ? "viajero" : "viajeros"} en {NOMBRE_CLASE[clase]}. Las
              sillas no se bloquean hasta que inicies la compra.
            </DialogNotice>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="primary"
            disabled={enviando || datos.agotada}
            onClick={() => onConfirmar(clase, Number(viajeros))}
          >
            {enviando ? "Agregando…" : "Agregar al carrito"}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Volver
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
