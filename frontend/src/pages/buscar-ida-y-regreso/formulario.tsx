import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Glass } from "@/components/ui/glass";
import { useCiudades } from "../programar-vuelo/api";
import {
  CAMPOS_BUSQUEDA,
  validarBusqueda,
  type CampoBusqueda,
  type ErroresBusqueda,
  type Parametros,
} from "./esquema";

const ELIGE = { value: "", label: "Elige una ciudad" };
const VIAJEROS = ["1", "2", "3", "4", "5"];

/** Ciudad de salida, de destino y de regreso (puede ser otra), fecha de ida y de regreso y
 *  viajeros (HU-21). Los errores de la pantalla se marcan junto al campo antes de enviar; los
 *  del servidor llegan en `errores`. */
export function FormularioTrayecto({
  aplicados,
  errores,
  onBuscar,
}: {
  aplicados: Parametros;
  errores: ErroresBusqueda;
  onBuscar: (valores: Pick<Parametros, CampoBusqueda | "viajeros">) => void;
}) {
  const [borrador, setBorrador] = useState(aplicados);
  const [propios, setPropios] = useState<ErroresBusqueda>({});
  const { data: ciudades = [] } = useCiudades();
  const opciones = [ELIGE, ...ciudades.map((c) => ({ value: c.codigo, label: c.nombre }))];

  const campo = (clave: CampoBusqueda | "viajeros") => ({
    value: borrador[clave],
    onChange: (e: { target: { value: string } }) => {
      setBorrador((b) => ({ ...b, [clave]: e.target.value }));
      if (clave !== "viajeros") setPropios((p) => ({ ...p, [clave]: undefined }));
    },
    error: clave === "viajeros" ? undefined : (propios[clave] ?? errores[clave]),
  });

  function buscar(e: FormEvent) {
    e.preventDefault();
    const invalidos = validarBusqueda(borrador);
    setPropios(invalidos);
    if (Object.keys(invalidos).length > 0) return;
    onBuscar({
      ...Object.fromEntries(CAMPOS_BUSQUEDA.map((c) => [c, borrador[c]])),
      viajeros: borrador.viajeros,
    } as Pick<Parametros, CampoBusqueda | "viajeros">);
  }

  return (
    <Glass>
      <form role="search" aria-label="Buscar ida y regreso" onSubmit={buscar} noValidate>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Ciudad de salida" options={opciones} {...campo("origen")} />
          <Field label="Ciudad de destino" options={opciones} {...campo("destino")} />
          <Field
            label="Ciudad de regreso"
            options={opciones}
            hint="Puede ser distinta de la de salida."
            {...campo("regreso")}
          />
          <Field label="Fecha de ida" type="date" {...campo("fecha_ida")} />
          <Field label="Fecha de regreso" type="date" {...campo("fecha_regreso")} />
          <Field label="Viajeros" options={VIAJEROS} {...campo("viajeros")} />
        </div>
        <div className="mt-4">
          <Button type="submit" variant="primary" icon="search">
            Buscar vuelos
          </Button>
        </div>
      </form>
    </Glass>
  );
}
