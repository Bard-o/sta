import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { useFiltros } from "./vuelos-programados/filtros";
import { FiltrosVuelos } from "./vuelos-programados/filtros-vuelos";

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
  const filtros = useFiltros();
  const { q, desde, hasta, pagina, periodoInvalido, hayFiltros, cambiar } = filtros;
  const [aCancelar, setACancelar] = useState<VueloAdmin | null>(null);

  const consulta = useVuelosProgramados({ q, desde, hasta, pagina }, !periodoInvalido);
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

      <FiltrosVuelos
        filtros={filtros}
        nombre="Filtrar vuelos"
        etiquetas={{
          q: "Buscar por código o ciudad",
          desde: "Salida desde",
          hasta: "Salida hasta",
        }}
        placeholder="STA-00031, Pereira…"
      />

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
                    <Button size="sm" href={`/admin/vuelos/${v.id}/promocion`}>
                      Promoción<span className="sr-only"> {v.codigo}</span>
                    </Button>
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
