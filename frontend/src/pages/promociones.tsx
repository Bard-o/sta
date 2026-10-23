import { useSearchParams } from "react-router";
import { Badge, type Tone } from "@/components/ui/badge";
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
import { fecha, hora, ZONA_COLOMBIA } from "@/lib/format";
import { POR_PAGINA, usePromociones, type EstadoPromocion } from "./promociones/api";
import { nombreClase } from "./promociones/esquema";

const ESTADOS: { value: "" | EstadoPromocion; label: string }[] = [
  { value: "", label: "Todas" },
  { value: "vigente", label: "Vigentes" },
  { value: "programada", label: "Programadas" },
  { value: "vencida", label: "Vencidas" },
  { value: "agotada", label: "Agotadas" },
  { value: "cancelada", label: "Canceladas" },
];

const TONO: Record<EstadoPromocion, Tone> = {
  vigente: "success",
  programada: "info",
  vencida: "neutral",
  agotada: "accent",
  cancelada: "danger",
};

const NOMBRE_ESTADO: Record<EstadoPromocion, string> = {
  vigente: "Vigente",
  programada: "Programada",
  vencida: "Vencida",
  agotada: "Agotada",
  cancelada: "Cancelada",
};

const esEstado = (v: string | null): v is EstadoPromocion =>
  ESTADOS.some((e) => e.value !== "" && e.value === v);

/** Vigencia en hora de Colombia: «15/10/2026 10:00 → 12:00» (o con la fecha de fin si cambia). */
function vigencia(inicio: string, fin: string) {
  const dia = fecha(inicio, ZONA_COLOMBIA);
  const finDia = fecha(fin, ZONA_COLOMBIA);
  return `${dia} ${hora(inicio, ZONA_COLOMBIA)} → ${
    finDia === dia ? "" : `${finDia} `
  }${hora(fin, ZONA_COLOMBIA)}`;
}

/** Promociones (HU-17): las de todos los vuelos, con su estado. Se crean desde Vuelos programados. */
export function PromocionesPage() {
  const [params, setParams] = useSearchParams();
  const parametro = params.get("estado");
  const estado = esEstado(parametro) ? parametro : "";
  const pagina = Math.max(1, Number(params.get("pagina")) || 1);
  const consulta = usePromociones(estado, pagina);
  const promociones = consulta.data?.items ?? [];

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

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="sta-h1">Promociones</h1>
          <p className="sta-sub">
            Para crear una promoción, elige el vuelo en Vuelos programados y usa «Promoción».
          </p>
        </div>
        <Button variant="secondary" href="/admin/vuelos">
          Ir a vuelos programados
        </Button>
      </div>

      <form role="search" aria-label="Filtrar promociones" onSubmit={(e) => e.preventDefault()}>
        <Field
          label="Estado"
          className="sm:max-w-xs"
          options={ESTADOS.map((e) => ({ value: e.value, label: e.label }))}
          value={estado}
          onChange={(e) => cambiar({ estado: e.target.value, pagina: "" })}
        />
      </form>

      {consulta.isError && <Notice tone="danger">{consulta.error.message}</Notice>}
      {consulta.isPending && (
        <p role="status" className="body sta-muted">
          Cargando promociones…
        </p>
      )}
      {consulta.data && promociones.length === 0 && (
        <p className="body sta-muted">
          {estado ? "No hay promociones en este estado." : "Todavía no hay promociones."}
        </p>
      )}

      {promociones.length > 0 && (
        <Table aria-label="Promociones">
          <TableHeader>
            <TableRow>
              <TableHead>Vuelo</TableHead>
              <TableHead>Ruta</TableHead>
              <TableHead align="right">Descuento</TableHead>
              <TableHead>Clases</TableHead>
              <TableHead>Vigencia (hora de Colombia)</TableHead>
              <TableHead>Estado</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {promociones.map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.vuelo_codigo}</TableCell>
                <TableCell>
                  {p.origen.nombre} → {p.destino.nombre}
                </TableCell>
                <TableCell align="right">{p.porcentaje} %</TableCell>
                <TableCell>{p.clases.map(nombreClase).join(" y ")}</TableCell>
                <TableCell>{vigencia(p.inicio, p.fin)}</TableCell>
                <TableCell>
                  <Badge tone={TONO[p.estado]}>{NOMBRE_ESTADO[p.estado]}</Badge>
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
  );
}
