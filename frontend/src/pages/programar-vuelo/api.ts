import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export type VueloEntrada = Schemas["VueloEntrada"];

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
