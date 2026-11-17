import { useQuery } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import { aConsulta, type Filtros, type Orden } from "./filtros";

export type VueloBusqueda = Schemas["VueloBusqueda"];
export type PaginaBusqueda = Schemas["PaginaVuelosBusqueda"];

export const POR_PAGINA = 20;

/** Búsqueda pública de vuelos (HU-20). Con `habilitado = false` (un rango que la pantalla ya
 *  sabe inválido) no consulta. Al cambiar de página o de filtro se conserva la lista anterior
 *  hasta que llega la nueva, para que no parpadee. */
export function useBuscarVuelos(
  filtros: Filtros,
  orden: Orden,
  pagina: number,
  habilitado: boolean,
) {
  const consulta = aConsulta(filtros, orden, pagina);
  return useQuery({
    queryKey: ["busqueda", "vuelos", consulta],
    enabled: habilitado,
    placeholderData: (anterior) => anterior,
    queryFn: () => unwrap(api.GET("/api/v1/busqueda/vuelos", { params: { query: consulta } })),
  });
}
