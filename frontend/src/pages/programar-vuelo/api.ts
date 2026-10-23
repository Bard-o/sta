import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export type VueloEntrada = Schemas["VueloEntrada"];
export type SerieEntrada = Schemas["SerieVuelosEntrada"];
export type SerieSalida = Schemas["SerieVuelosSalida"];

/** Catálogo de ciudades (RF-12): casi no cambia, así que se pide una vez. */
export function useCiudades() {
  return useQuery({
    queryKey: ["ciudades"],
    queryFn: () => unwrap(api.GET("/api/v1/ciudades")),
    staleTime: Infinity,
  });
}

/** Vista previa «Así lo verá el cliente»: aplica las mismas validaciones que guardar y no guarda
 *  nada. Sin `entrada` (formulario incompleto) no consulta. */
export function useVistaPrevia(entrada: VueloEntrada | null) {
  return useQuery({
    queryKey: ["vuelos", "vista-previa", entrada],
    enabled: entrada !== null,
    retry: false,
    queryFn: () =>
      unwrap(api.POST("/api/v1/vuelos/vista-previa", { body: entrada as VueloEntrada })),
  });
}

/** Publica el vuelo (HU-13): el servidor crea también su noticia y el elemento del carrusel. */
export function usePublicarVuelo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: VueloEntrada) => unwrap(api.POST("/api/v1/vuelos", { body: datos })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vuelos"] });
      void queryClient.invalidateQueries({ queryKey: ["noticias"] });
    },
  });
}

/** Vista previa de la serie (HU-14): fechas que se crearían y las que se omitirían, sin guardar. */
export function useVistaSerie(entrada: SerieEntrada | null) {
  return useQuery({
    queryKey: ["vuelos", "vista-previa-serie", entrada],
    enabled: entrada !== null,
    retry: false,
    queryFn: () =>
      unwrap(
        api.POST("/api/v1/vuelos/recurrentes/vista-previa", { body: entrada as SerieEntrada }),
      ),
  });
}

/** Publica la serie: un vuelo independiente (con su noticia) por cada fecha. */
export function usePublicarSerie() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datos: SerieEntrada) =>
      unwrap(api.POST("/api/v1/vuelos/recurrentes", { body: datos })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vuelos"] });
      void queryClient.invalidateQueries({ queryKey: ["noticias"] });
    },
  });
}
