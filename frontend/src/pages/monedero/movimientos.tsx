import { ApiError } from "@/api/client";
import { MOVIMIENTOS_POR_PAGINA, useMovimientos, type FiltrosMovimientos } from "@/auth/monedero";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Pager } from "@/components/ui/pager";
import { Segmented } from "@/components/ui/segmented";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cop, fechaHora, ZONA_COLOMBIA } from "@/lib/format";

const TIPOS: { value: FiltrosMovimientos["tipo"]; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "recarga", label: "Recargas" },
  { value: "compra", label: "Compras" },
  { value: "reembolso", label: "Reembolsos" },
];

const NOMBRE_TIPO = { recarga: "Recarga", compra: "Compra", reembolso: "Reembolso" } as const;

export const MENSAJE_RANGO = "La fecha final no puede ser anterior a la inicial.";

/** «Movimientos» (HU-31): del más reciente al más antiguo, con fecha, tipo, referencia, valor con
 *  signo y saldo resultante; filtra por tipo y por fecha (hora de Colombia). El saldo es siempre
 *  la suma de los movimientos. */
export function Movimientos({
  filtros,
  onCambiar,
}: {
  filtros: FiltrosMovimientos;
  onCambiar: (cambios: Partial<Record<"tipo" | "desde" | "hasta" | "pagina", string>>) => void;
}) {
  const rangoInvalido =
    filtros.desde !== "" && filtros.hasta !== "" && filtros.hasta < filtros.desde;
  const movimientos = useMovimientos(filtros, !rangoInvalido);
  const errorDeRango =
    rangoInvalido ||
    (movimientos.error instanceof ApiError && movimientos.error.codigo === "rango_invalido");
  const items = movimientos.data?.items ?? [];
  const hayFiltros = filtros.tipo !== "" || filtros.desde !== "" || filtros.hasta !== "";

  return (
    <section className="flex min-w-0 flex-1 flex-col gap-4" aria-label="Movimientos">
      <div className="sta-between">
        <h2 className="sta-h1">Movimientos</h2>
        <Segmented
          label="Tipo de movimiento"
          options={TIPOS}
          value={filtros.tipo}
          onChange={(tipo) => onCambiar({ tipo, pagina: "" })}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Desde"
          type="date"
          value={filtros.desde}
          onChange={(e) => onCambiar({ desde: e.target.value, pagina: "" })}
        />
        <Field
          label="Hasta"
          type="date"
          value={filtros.hasta}
          error={errorDeRango ? MENSAJE_RANGO : undefined}
          onChange={(e) => onCambiar({ hasta: e.target.value, pagina: "" })}
        />
      </div>

      {movimientos.isPending && !rangoInvalido && (
        <p role="status" className="body sta-muted">
          Cargando tus movimientos…
        </p>
      )}
      {movimientos.isError && !errorDeRango && (
        <Notice tone="danger">{movimientos.error.message}</Notice>
      )}

      {movimientos.data && items.length === 0 && !rangoInvalido && (
        <div className="flex flex-col items-start gap-3">
          <p className="body sta-muted">
            {hayFiltros
              ? "No hay movimientos con estos filtros."
              : "Todavía no tienes movimientos. Cuando recargues o compres, aparecerán aquí."}
          </p>
          {hayFiltros ? (
            <Button onClick={() => onCambiar({ tipo: "", desde: "", hasta: "", pagina: "" })}>
              Quitar filtros
            </Button>
          ) : (
            <Button href="/monedero/recargar">Recargar monedero</Button>
          )}
        </div>
      )}

      {items.length > 0 && (
        <Table aria-label="Movimientos del monedero">
          <TableHeader>
            <TableRow>
              <TableHead>Fecha</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead>Referencia</TableHead>
              <TableHead align="right">Valor</TableHead>
              <TableHead align="right">Saldo</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((m) => (
              <TableRow key={m.id}>
                <TableCell>{fechaHora(m.creado_en, ZONA_COLOMBIA)}</TableCell>
                <TableCell>{NOMBRE_TIPO[m.tipo]}</TableCell>
                <TableCell>
                  <span className="sta-code">{m.referencia}</span>
                </TableCell>
                <TableCell align="right">
                  <span className={m.valor >= 0 ? "sta-pos" : "sta-neg"}>
                    {cop(m.valor, { sign: true })}
                  </span>
                </TableCell>
                <TableCell align="right">
                  <strong>{cop(m.saldo_resultante)}</strong>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {movimientos.data && (
        <Pager
          pagina={movimientos.data.pagina}
          total={movimientos.data.total}
          porPagina={MOVIMIENTOS_POR_PAGINA}
          onChange={(p) => onCambiar({ pagina: p === 1 ? "" : String(p) })}
        />
      )}
      <p className="caption sta-muted">
        El saldo es siempre la suma de tus movimientos y nunca queda negativo.
      </p>
    </section>
  );
}
