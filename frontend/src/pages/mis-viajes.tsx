import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { Pager } from "@/components/ui/pager";
import { Segmented } from "@/components/ui/segmented";
import { useSaldo } from "./compra-pago/api";
import { POR_PAGINA, useMisViajes, type EstadoReserva, type TipoViaje } from "./mis-viajes/api";
import {
  ESTADOS_RESERVA,
  leerEstado,
  leerMes,
  leerPagina,
  leerTipo,
  opcionesDeMes,
} from "./mis-viajes/filtros";
import { TarjetaCompra } from "./mis-viajes/tarjeta-compra";
import { TarjetaReserva } from "./mis-viajes/tarjeta-reserva";

const TIPOS: { value: TipoViaje; label: string }[] = [
  { value: "reserva", label: "Reservas" },
  { value: "compra", label: "Compras" },
];

/** S19 Mis viajes (HU-27): las reservas y las compras del cliente, de la más reciente a la más
 *  antigua, con filtro por estado y por mes. Una reserva vigente se paga aquí, completa o por
 *  viajero. Cancelar (HU-34, HU-35) y el histórico (HU-36) llegan en la iteración 3. */
export function MisViajesPage() {
  const [params, setParams] = useSearchParams();
  const tipo = leerTipo(params);
  const estado = leerEstado(params);
  const mes = leerMes(params);
  const pagina = leerPagina(params);
  const reservaAPagar = Number(params.get("pagar")) || null;

  const viajes = useMisViajes({ tipo, estado: tipo === "reserva" ? estado : "", mes, pagina });
  const saldo = useSaldo();
  const meses = useMemo(() => opcionesDeMes(mes), [mes]);

  function escribir(cambios: Record<string, string>) {
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

  const items = viajes.data?.items ?? [];
  const hayFiltros = estado !== "" || mes !== "";
  const plural = tipo === "reserva" ? "reservas" : "compras";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">Mis viajes</h1>
        <p className="sta-sub">
          {tipo === "reserva"
            ? "Las reservas congelan el precio y las sillas hasta que vencen. Paga a todos los viajeros o solo a algunos."
            : "Tus compras pagadas, con sus sillas y el código de reserva."}
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Segmented
          label="Tipo de viaje"
          options={TIPOS}
          value={tipo}
          onChange={(valor) =>
            escribir({ tipo: valor === "reserva" ? "" : valor, estado: "", pagina: "", pagar: "" })
          }
        />
        {tipo === "reserva" && (
          <Segmented<EstadoReserva | "">
            label="Estado de la reserva"
            options={ESTADOS_RESERVA}
            value={estado}
            onChange={(valor) => escribir({ estado: valor, pagina: "", pagar: "" })}
          />
        )}
        <Field
          label="Mes de salida"
          options={meses}
          value={mes}
          onChange={(e) => escribir({ mes: e.target.value, pagina: "", pagar: "" })}
        />
      </div>

      {viajes.isPending && (
        <p role="status" className="body sta-muted">
          Cargando tus {plural}…
        </p>
      )}
      {viajes.isError && <Notice tone="danger">{viajes.error.message}</Notice>}

      {viajes.data && items.length === 0 && (
        <Glass
          title={hayFiltros ? `No hay ${plural} con estos filtros` : `Todavía no tienes ${plural}`}
        >
          <div className="flex flex-col items-start gap-4">
            <p className="body sta-muted">
              {hayFiltros
                ? "Cambia el estado o el mes para ver más."
                : "Busca un vuelo y agrégalo al carrito para reservarlo o comprarlo."}
            </p>
            {hayFiltros ? (
              <Button onClick={() => setParams({ tipo }, { replace: true })}>Quitar filtros</Button>
            ) : (
              <Button variant="primary" icon="search" href="/buscar">
                Buscar vuelos
              </Button>
            )}
          </div>
        </Glass>
      )}

      {items.map((viaje) =>
        tipo === "reserva" ? (
          <TarjetaReserva
            key={viaje.id}
            reserva={viaje}
            saldo={saldo.data?.saldo}
            destacada={viaje.id === reservaAPagar}
          />
        ) : (
          <TarjetaCompra key={viaje.id} compra={viaje} />
        ),
      )}

      {viajes.data && (
        <Pager
          pagina={viajes.data.pagina}
          total={viajes.data.total}
          porPagina={POR_PAGINA}
          onChange={(p) => escribir({ pagina: p === 1 ? "" : String(p) })}
        />
      )}
    </div>
  );
}
