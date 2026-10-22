import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
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
import { nombreClase } from "./promociones/esquema";
import { POR_PAGINA, useVuelosAdmin, type VueloAdmin } from "./vuelos-programados/api";
import { useFiltros } from "./vuelos-programados/filtros";
import { FiltrosVuelos } from "./vuelos-programados/filtros-vuelos";
import { OcupacionPorClase } from "./vuelos-programados/ocupacion";
import { usePasajerosVuelo } from "./vuelos-realizados/api";

const vendidos = (v: VueloAdmin) => v.ocupacion.primera.vendidas + v.ocupacion.economica.vendidas;

/** Pasajeros de un vuelo realizado, con su clase y su silla, y la ocupación por clase. */
function PanelPasajeros({ vueloId, codigo }: { vueloId: number | null; codigo?: string }) {
  const consulta = usePasajerosVuelo(vueloId);

  if (vueloId === null) {
    return (
      <Glass title="Pasajeros" className="min-w-0">
        <p className="body sta-muted">
          Elige un vuelo de la lista para ver sus pasajeros y su ocupación.
        </p>
      </Glass>
    );
  }
  const titulo = `Pasajeros de ${consulta.data?.vuelo.codigo ?? codigo ?? "este vuelo"}`;
  return (
    <Glass title={titulo} aria-live="polite" className="min-w-0">
      {consulta.isPending && (
        <p role="status" className="body sta-muted">
          Cargando pasajeros…
        </p>
      )}
      {consulta.isError && <Notice tone="danger">{consulta.error.message}</Notice>}
      {consulta.data && (
        <div className="flex flex-col gap-4">
          <OcupacionPorClase ocupacion={consulta.data.ocupacion} />
          {consulta.data.pasajeros.length === 0 ? (
            <p className="body sta-muted">Este vuelo no tiene pasajeros registrados.</p>
          ) : (
            <Table aria-label={titulo}>
              <TableHeader>
                <TableRow>
                  <TableHead>Pasajero</TableHead>
                  <TableHead>Clase</TableHead>
                  <TableHead>Silla</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {consulta.data.pasajeros.map((p) => (
                  <TableRow key={p.numero_silla}>
                    <TableCell>
                      {p.nombres} {p.apellidos}
                    </TableCell>
                    <TableCell>{nombreClase(p.clase)}</TableCell>
                    <TableCell>{p.silla}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </Glass>
  );
}

/** S12 · Vuelos realizados (HU-18): listado con filtros y, al elegir uno, sus pasajeros. */
export function VuelosRealizadosPage() {
  const filtros = useFiltros();
  const { q, desde, hasta, pagina, periodoInvalido, hayFiltros, params, cambiar } = filtros;
  const elegido = Number(params.get("vuelo")) || null;

  const consulta = useVuelosAdmin("realizado", { q, desde, hasta, pagina }, !periodoInvalido);
  const vuelos = consulta.data?.items ?? [];

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">Vuelos realizados</h1>
        <p className="sta-sub">
          Un vuelo pasa aquí automáticamente cuando se cumple su hora de llegada.
        </p>
      </div>

      <FiltrosVuelos
        filtros={filtros}
        nombre="Filtrar vuelos realizados"
        etiquetas={{ q: "Ruta o código", desde: "Llegada desde", hasta: "Llegada hasta" }}
        placeholder="Buscar"
      />

      {consulta.isError && <Notice tone="danger">{consulta.error.message}</Notice>}
      {consulta.isPending && !periodoInvalido && (
        <p role="status" className="body sta-muted">
          Cargando vuelos…
        </p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-4">
          {consulta.data && vuelos.length === 0 && (
            <p className="body sta-muted">
              {hayFiltros
                ? "No hay vuelos realizados con estos filtros."
                : "Todavía no hay vuelos realizados."}
            </p>
          )}
          {vuelos.length > 0 && (
            <Table aria-label="Vuelos realizados">
              <TableHeader>
                <TableRow>
                  <TableHead>Llegada</TableHead>
                  <TableHead>Vuelo</TableHead>
                  <TableHead>Ruta</TableHead>
                  <TableHead align="right">Ocupación</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {vuelos.map((v) => (
                  <TableRow key={v.id} highlighted={v.id === elegido}>
                    <TableCell>{fechaHora(v.llegada, v.destino.zona_horaria)}</TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-pressed={v.id === elegido}
                        aria-label={`Ver pasajeros de ${v.codigo}`}
                        onClick={() => cambiar({ vuelo: String(v.id) })}
                      >
                        {v.codigo}
                      </Button>
                    </TableCell>
                    <TableCell>
                      {v.origen.nombre} → {v.destino.nombre}
                    </TableCell>
                    <TableCell align="right">
                      {vendidos(v)} / {v.capacidad.total}
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
        </div>

        <PanelPasajeros vueloId={elegido} codigo={vuelos.find((v) => v.id === elegido)?.codigo} />
      </div>
    </div>
  );
}
