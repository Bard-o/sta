import { Link, useParams } from "react-router";
import { ApiError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { FlightPass } from "@/components/ui/flight-pass";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cop, desfase, duracion, fecha, fechaHora, hora, ZONA_COLOMBIA } from "@/lib/format";
import { NoEncontradaPage } from "./no-encontrada";
import { useVueloDetalle } from "./noticias-comunes/api";
import { NOMBRE_CLASE, type ClaseVuelo } from "./noticias-comunes/estado";

const AVISO_ESTADO = {
  realizado: "Este vuelo ya se realizó y no está disponible para la venta.",
  cancelado: "Este vuelo fue cancelado y no está disponible.",
} as const;

/** Detalle público de un vuelo (HU-19): lo abren las noticias y el carrusel. Horas locales de cada
 *  ciudad con su desfase (IU-05, RF-15) y aviso si el vuelo ya no está programado. */
export function VueloDetallePage() {
  const { vueloId } = useParams();
  const id = Number(vueloId);
  const valido = Number.isInteger(id) && id > 0;
  const vuelo = useVueloDetalle(id);

  if (!valido) return <NoEncontradaPage />;
  if (vuelo.isPending) return <p className="body sta-muted">Cargando vuelo…</p>;
  if (vuelo.isError) {
    const noExiste = vuelo.error instanceof ApiError && vuelo.error.status === 404;
    return (
      <div className="flex flex-col gap-4">
        <Notice tone="danger">
          {noExiste
            ? "No encontramos este vuelo."
            : "No pudimos cargar el vuelo. Intenta de nuevo."}
        </Notice>
        <p>
          <Link className="sta-link" to="/noticias">
            Volver a las noticias
          </Link>
        </p>
      </div>
    );
  }

  const v = vuelo.data;
  const programado = v.estado === "programado";
  const zo = v.origen.zona_horaria;
  const zd = v.destino.zona_horaria;
  const clases: ClaseVuelo[] = ["economica", "primera"];
  const disponibles = clases.filter((c) => !v[c].agotada);
  const desde = disponibles.length ? Math.min(...disponibles.map((c) => v[c].precio_vigente)) : 0;
  const llegaOtroDia = fecha(v.llegada, zd) !== fecha(v.salida, zo);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="sta-h1">
          {v.origen.nombre} → {v.destino.nombre}
        </h1>
        <p className="sta-sub">
          Vuelo {v.codigo} · {v.tipo === "nacional" ? "Nacional" : "Internacional"}
        </p>
      </div>

      {!programado && (
        <Notice tone="danger">{AVISO_ESTADO[v.estado as keyof typeof AVISO_ESTADO]}</Notice>
      )}

      <FlightPass
        state={programado && disponibles.length > 0 ? "default" : "soldout"}
        code={v.codigo}
        from={{
          iata: v.origen.codigo,
          city: v.origen.nombre,
          time: hora(v.salida, zo),
          tz: desfase(v.salida, zo),
        }}
        to={{
          iata: v.destino.codigo,
          city: v.destino.nombre,
          time: llegaOtroDia
            ? `${hora(v.llegada, zd)} · ${fecha(v.llegada, zd)}`
            : hora(v.llegada, zd),
          tz: desfase(v.llegada, zd),
        }}
        duration={duracion(v.duracion_minutos)}
        date={`Salida ${fecha(v.salida, zo)}`}
        price={disponibles.length ? cop(desde) : "Agotado"}
        priceNote={disponibles.length ? "Desde, por persona" : undefined}
        badges={
          !programado
            ? [
                {
                  tone: "danger",
                  icon: "x",
                  label: v.estado === "cancelado" ? "Cancelado" : "Realizado",
                },
              ]
            : disponibles.length === 0
              ? [{ tone: "danger", icon: "x", label: "Agotado" }]
              : []
        }
      />

      <Glass title="Clases y precios">
        <Table>
          <TableHeader>
            <tr>
              <TableHead>Clase</TableHead>
              <TableHead align="right">Precio</TableHead>
              <TableHead align="right">Libres</TableHead>
            </tr>
          </TableHeader>
          <TableBody>
            {clases.map((c) => {
              const d = v[c];
              const promo = d.promocion?.estado === "vigente" ? d.promocion : null;
              return (
                <TableRow key={c}>
                  <TableCell>
                    <span className="body-strong">{NOMBRE_CLASE[c]}</span>
                    {promo && (
                      <>
                        {" "}
                        <Badge tone="accent" icon="tag">
                          Promoción −{promo.porcentaje} %
                        </Badge>
                        <div className="caption sta-muted">
                          Hasta el {fechaHora(promo.fin, ZONA_COLOMBIA)} hora de Colombia
                        </div>
                      </>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    {promo && <s className="sta-pass__old">{cop(d.precio_base)} </s>}
                    <span className="sta-num">{cop(d.precio_vigente)}</span>
                  </TableCell>
                  <TableCell align="right">
                    {d.agotada ? (
                      <Badge tone="danger" icon="x">
                        Agotada
                      </Badge>
                    ) : (
                      <span className="sta-num">{d.disponibles}</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <p className="caption sta-muted mt-3">
          Las horas son locales de cada ciudad. La reserva y la compra llegan en la siguiente
          iteración.
        </p>
      </Glass>
    </div>
  );
}
