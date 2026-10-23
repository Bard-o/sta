import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Pager } from "@/components/ui/pager";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fechaHora } from "@/lib/format";
import { POR_PAGINA, useVuelosProgramados, type VueloAdmin } from "./vuelos-programados/api";
import { CancelarVueloDialogo } from "./vuelos-programados/cancelar-dialogo";

/** Estado comercial del vuelo, siempre con palabras (el color no va solo). */
function EstadoVenta({ vuelo }: { vuelo: VueloAdmin }) {
  if (vuelo.tiquetes_vendidos > 0) {
    return (
      <Badge tone="success">
        {vuelo.tiquetes_vendidos}{" "}
        {vuelo.tiquetes_vendidos === 1 ? "tiquete vendido" : "tiquetes vendidos"}
      </Badge>
    );
  }
  if (vuelo.reservas_activas > 0) {
    return (
      <Badge tone="info">
        {vuelo.reservas_activas}{" "}
        {vuelo.reservas_activas === 1 ? "reserva activa" : "reservas activas"}
      </Badge>
    );
  }
  return <Badge>Sin ventas</Badge>;
}

const ocupadas = (v: VueloAdmin) =>
  v.ocupacion.primera.vendidas +
  v.ocupacion.primera.reservadas +
  v.ocupacion.economica.vendidas +
  v.ocupacion.economica.reservadas;

/** S09 · Vuelos programados (HU-15, HU-16): filtros, edición y cancelación sin ventas. */
export function VuelosProgramadosPage() {
  const [params, setParams] = useSearchParams();
  const desde = params.get("desde") ?? "";
  const hasta = params.get("hasta") ?? "";
  const q = params.get("q") ?? "";
  const pagina = Math.max(1, Number(params.get("pagina")) || 1);

  const [texto, setTexto] = useState(q);
  const [aCancelar, setACancelar] = useState<VueloAdmin | null>(null);
  const temporizador = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(temporizador.current), []);

  function cambiar(cambios: Record<string, string>) {
    setParams(
      (previos) => {
        const siguiente = new URLSearchParams(previos);
        for (const [clave, valor] of Object.entries(cambios)) {
          if (valor) siguiente.set(clave, valor);
          else siguiente.delete(clave);
        }
        return siguiente;
      },
      { replace: true },
    );
  }

  // El texto se aplica al dejar de escribir (no una petición por tecla) y vuelve a la página 1.
  // `setParams` no encola: el temporizador debe usar el `cambiar` del último render, no el viejo.
  const cambiarActual = useRef(cambiar);
  useEffect(() => {
    cambiarActual.current = cambiar;
  });

  function escribir(valor: string) {
    setTexto(valor);
    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(
      () => cambiarActual.current({ q: valor.trim(), pagina: "" }),
      400,
    );
  }

  const periodoInvalido = desde !== "" && hasta !== "" && hasta < desde;
  const consulta = useVuelosProgramados({ q, desde, hasta, pagina }, !periodoInvalido);
  const hayFiltros = q !== "" || desde !== "" || hasta !== "";
  const vuelos = consulta.data?.items ?? [];

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="sta-h1">Vuelos programados</h1>
          <p className="sta-sub">Un vuelo con reservas activas o compras no se puede editar.</p>
        </div>
        <Button variant="primary" href="/admin/vuelos/nuevo">
          Programar vuelo
        </Button>
      </div>

      <form
        role="search"
        aria-label="Filtrar vuelos"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(e) => e.preventDefault()}
      >
        <Field
          label="Buscar por código o ciudad"
          className="lg:col-span-2"
          icon="search"
          value={texto}
          onChange={(e) => escribir(e.target.value)}
          placeholder="STA-00031, Pereira…"
        />
        <Field
          label="Salida desde"
          type="date"
          value={desde}
          onChange={(e) => cambiar({ desde: e.target.value, pagina: "" })}
        />
        <Field
          label="Salida hasta"
          type="date"
          value={hasta}
          min={desde || undefined}
          error={periodoInvalido ? "La fecha final no puede ser anterior a la inicial." : undefined}
          onChange={(e) => cambiar({ hasta: e.target.value, pagina: "" })}
        />
      </form>

      {hayFiltros && (
        <div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              clearTimeout(temporizador.current);
              setTexto("");
              setParams({}, { replace: true });
            }}
          >
            Limpiar filtros
          </Button>
        </div>
      )}

      {consulta.isError && <Notice tone="danger">{consulta.error.message}</Notice>}
      {consulta.isPending && !periodoInvalido && (
        <p role="status" className="body sta-muted">
          Cargando vuelos…
        </p>
      )}

      {consulta.data && vuelos.length === 0 && (
        <p className="body sta-muted">
          {hayFiltros
            ? "No hay vuelos programados con estos filtros."
            : "Todavía no hay vuelos programados."}
        </p>
      )}

      {vuelos.length > 0 && (
        <Table aria-label="Vuelos programados">
          <TableHeader>
            <TableRow>
              <TableHead>Salida</TableHead>
              <TableHead>Vuelo</TableHead>
              <TableHead>Ruta</TableHead>
              <TableHead align="right">Ocupación</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>
                <span className="sr-only">Acciones</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {vuelos.map((v) => (
              <TableRow key={v.id}>
                <TableCell>{fechaHora(v.salida, v.origen.zona_horaria)}</TableCell>
                <TableCell>{v.codigo}</TableCell>
                <TableCell>
                  {v.origen.nombre} → {v.destino.nombre}
                </TableCell>
                <TableCell align="right">
                  {ocupadas(v)} / {v.capacidad.total}
                </TableCell>
                <TableCell>
                  <div className="flex flex-col items-start gap-1">
                    <EstadoVenta vuelo={v} />
                    {!v.editable && v.motivo_no_editable && (
                      <span className="caption sta-muted whitespace-normal">
                        {v.motivo_no_editable}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    {v.editable ? (
                      <Button size="sm" href={`/admin/vuelos/${v.id}/editar`}>
                        Editar<span className="sr-only"> {v.codigo}</span>
                      </Button>
                    ) : (
                      <Button size="sm" disabled>
                        Editar<span className="sr-only"> {v.codigo}</span>
                      </Button>
                    )}
                    {v.cancelable ? (
                      <Button size="sm" onClick={() => setACancelar(v)}>
                        Cancelar<span className="sr-only"> {v.codigo}</span>
                      </Button>
                    ) : (
                      v.tiquetes_vendidos > 0 && (
                        <Button
                          size="sm"
                          disabled
                          title="Un vuelo con tiquetes vendidos solo se cancela por fuerza mayor."
                        >
                          Fuerza mayor<span className="sr-only"> {v.codigo}</span>
                        </Button>
                      )
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {consulta.data && (
        <Pager
          pagina={consulta.data.pagina}
          total={consulta.data.total}
          porPagina={POR_PAGINA}
          onChange={(p) => cambiar({ pagina: p === 1 ? "" : String(p) })}
        />
      )}

      <CancelarVueloDialogo vuelo={aCancelar} onClose={() => setACancelar(null)} />
    </div>
  );
}
