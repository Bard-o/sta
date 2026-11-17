import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Glass } from "@/components/ui/glass";
import { useCiudades } from "../programar-vuelo/api";
import {
  CLAVES_FILTRO,
  FILTROS_VACIOS,
  FRANJAS,
  hayFiltros,
  validarRangos,
  type ClaveFiltro,
  type Filtros,
} from "./filtros";

export type ErroresFiltros = Partial<Record<ClaveFiltro, string>>;

const CUALQUIERA = { value: "", label: "Cualquiera" };

/** Los nueve filtros de HU-20 (S14). Se editan en un borrador y se aplican con «Aplicar filtros»,
 *  como en el wireframe; los rangos inválidos se marcan junto al campo antes de enviar y también
 *  los que rechaza el servidor (`errores`). */
export function FiltrosBusqueda({
  aplicados,
  errores,
  onAplicar,
  onLimpiar,
}: {
  aplicados: Filtros;
  /** Errores de los filtros que ya están aplicados (de la pantalla o del servidor). */
  errores: ErroresFiltros;
  onAplicar: (filtros: Filtros) => void;
  onLimpiar: () => void;
}) {
  const [borrador, setBorrador] = useState<Filtros>(aplicados);
  const [propios, setPropios] = useState<ErroresFiltros>({});
  const { data: ciudades = [] } = useCiudades();

  const ciudadesOpciones = [
    CUALQUIERA,
    ...ciudades.map((c) => ({ value: c.codigo, label: c.nombre })),
  ];
  const error = (clave: ClaveFiltro) => propios[clave] ?? errores[clave];
  const campo = (clave: ClaveFiltro) => ({
    value: borrador[clave],
    onChange: (e: { target: { value: string } }) => {
      setBorrador((b) => ({ ...b, [clave]: e.target.value }));
      setPropios((p) => ({ ...p, [clave]: undefined }));
    },
    error: error(clave),
  });

  function aplicar(e: FormEvent) {
    e.preventDefault();
    const invalidos = validarRangos(borrador);
    setPropios(invalidos);
    if (Object.keys(invalidos).length === 0) onAplicar(borrador);
  }

  function limpiar() {
    setBorrador(FILTROS_VACIOS);
    setPropios({});
    onLimpiar();
  }

  return (
    <Glass title="Filtros">
      <form role="search" aria-label="Filtros de búsqueda" onSubmit={aplicar} noValidate>
        <div className="flex flex-col gap-3">
          <Field
            label="Código del vuelo"
            icon="search"
            placeholder="STA-00031"
            maxLength={20}
            {...campo("codigo")}
          />
          <Field label="Origen" options={ciudadesOpciones} {...campo("origen")} />
          <Field label="Destino" options={ciudadesOpciones} {...campo("destino")} />
          <Field
            label="Tipo"
            options={[
              CUALQUIERA,
              { value: "nacional", label: "Nacional" },
              { value: "internacional", label: "Internacional" },
            ]}
            {...campo("tipo")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Salida desde" type="date" {...campo("fecha_desde")} />
            <Field label="Salida hasta" type="date" {...campo("fecha_hasta")} />
          </div>
          <Field
            label="Franja horaria"
            options={[CUALQUIERA, ...FRANJAS.map((f) => ({ value: f.value, label: f.label }))]}
            hint="Hora local del origen."
            {...campo("franja")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Duración mín. (min)"
              type="number"
              inputMode="numeric"
              min={0}
              {...campo("duracion_min")}
            />
            <Field
              label="Duración máx. (min)"
              type="number"
              inputMode="numeric"
              min={0}
              {...campo("duracion_max")}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Precio mín. ($)"
              type="number"
              inputMode="numeric"
              min={0}
              {...campo("precio_min")}
            />
            <Field
              label="Precio máx. ($)"
              type="number"
              inputMode="numeric"
              min={0}
              {...campo("precio_max")}
            />
          </div>
          <Field
            label="Clase"
            options={[
              CUALQUIERA,
              { value: "economica", label: "Económica" },
              { value: "primera", label: "Primera clase" },
            ]}
            hint="Define el precio que se filtra y se ordena."
            {...campo("clase")}
          />
          <Button type="submit" variant="primary" block>
            Aplicar filtros
          </Button>
          {(hayFiltros(aplicados) || CLAVES_FILTRO.some((c) => borrador[c] !== "")) && (
            <Button type="button" variant="ghost" block onClick={limpiar}>
              Quitar filtros
            </Button>
          )}
        </div>
      </form>
    </Glass>
  );
}
