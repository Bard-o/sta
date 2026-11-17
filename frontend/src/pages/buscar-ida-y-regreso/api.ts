import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { PaginaBusqueda } from "../buscar/api";
import type { Parametros } from "./esquema";

const POR_PAGINA = 20;

/** Paso 1 (HU-21): los vuelos de ida de ese día, en la hora local del origen. */
export function useIdas(p: Parametros, habilitado: boolean, pagina: number) {
  const query = {
    origen: p.origen,
    destino: p.destino,
    fecha_desde: p.fecha_ida,
    fecha_hasta: p.fecha_ida,
    orden: "fecha" as const,
    pagina,
    por_pagina: POR_PAGINA,
  };
  return useQuery({
    queryKey: ["busqueda", "idas", query],
    enabled: habilitado,
    placeholderData: (anterior) => anterior,
    queryFn: () => unwrap(api.GET("/api/v1/busqueda/vuelos", { params: { query } })),
  });
}

/** Paso 2 (HU-21, RF-28): solo los regresos que salen estrictamente después de la llegada de la
 *  ida elegida. Sin ida elegida no consulta. */
export function useRegresos(p: Parametros, idaId: number | null) {
  const query = {
    vuelo_ida_id: idaId ?? 0,
    destino: p.regreso,
    fecha: p.fecha_regreso,
    orden: "fecha" as const,
    por_pagina: POR_PAGINA,
  };
  return useQuery({
    queryKey: ["busqueda", "regresos", query],
    enabled: idaId !== null,
    queryFn: () => unwrap(api.GET("/api/v1/busqueda/regresos", { params: { query } })),
  });
}

/** Los vuelos del mismo día entre las mismas ciudades, para dibujar deshabilitados los que salen
 *  antes de la llegada de la ida (wireframe S15). El servidor no los devuelve como regresos. */
export function useVuelosDelDiaDeRegreso(p: Parametros, destinoDeLaIda: string | null) {
  const query = {
    origen: destinoDeLaIda ?? "",
    destino: p.regreso,
    fecha_desde: p.fecha_regreso,
    fecha_hasta: p.fecha_regreso,
    orden: "fecha" as const,
    por_pagina: POR_PAGINA,
  };
  return useQuery<PaginaBusqueda>({
    queryKey: ["busqueda", "regreso-del-dia", query],
    enabled: destinoDeLaIda !== null,
    queryFn: () => unwrap(api.GET("/api/v1/busqueda/vuelos", { params: { query } })),
  });
}
