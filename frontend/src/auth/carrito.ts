import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export type Carrito = Schemas["Carrito"];
export type SeleccionCarrito = Schemas["SeleccionCarrito"];
export type SeleccionCambio = Schemas["SeleccionCambio"];
export type SeleccionEntrada = Schemas["SeleccionEntrada"];

export const CARRITO_KEY = ["carrito"] as const;

/** El carrito del cliente con precio, cupo y avisos recalculados en cada lectura (HU-23). Con
 *  `habilitado = false` no consulta (visitantes, administrador y root no tienen carrito). */
export function useCarrito(habilitado = true) {
  return useQuery({
    queryKey: CARRITO_KEY,
    enabled: habilitado,
    queryFn: () => unwrap(api.GET("/api/v1/carrito")),
  });
}

/** Agrega un vuelo (o una ida y regreso) al carrito (HU-22). El servidor valida el vuelo, el
 *  límite de 5 y el cupo (`vuelo_no_disponible`, `fuera_de_plazo`, `limite_tiquetes`,
 *  `clase_agotada`); el contador del menú se actualiza al terminar. */
export function useAgregarSeleccion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entrada: SeleccionEntrada) =>
      unwrap(api.POST("/api/v1/carrito/selecciones", { body: entrada })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CARRITO_KEY });
    },
  });
}

/** Quita una selección de lo que ya está en caché, para que la lista y el contador del menú se
 *  actualicen sin esperar otra lectura. */
function sinSeleccion(queryClient: QueryClient, seleccionId: number) {
  queryClient.setQueryData<Carrito>(CARRITO_KEY, (carrito) => {
    if (!carrito) return carrito;
    const selecciones = carrito.selecciones.filter((s) => s.id !== seleccionId);
    return {
      selecciones,
      cantidad: selecciones.length,
      total: selecciones.filter((s) => s.confirmable).reduce((suma, s) => suma + s.subtotal, 0),
    };
  });
}

/** Cambia la clase de los tramos o la cantidad de viajeros; el servidor vuelve a validar el
 *  límite de 5 y el cupo (`limite_tiquetes`, `clase_agotada`). Se relee el carrito pase lo que
 *  pase: un error también puede significar que algo cambió. */
export function useCambiarSeleccion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, cambio }: { id: number; cambio: SeleccionCambio }) =>
      unwrap(
        api.PATCH("/api/v1/carrito/selecciones/{seleccion_id}", {
          params: { path: { seleccion_id: id } },
          body: cambio,
        }),
      ),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: CARRITO_KEY });
    },
  });
}

/** Quita una selección. Después de reservar o comprar, las pantallas de reserva y de pago la
 *  quitan con este mismo hook (`DELETE /carrito/selecciones/{id}`, #128 y #134). */
export function useQuitarSeleccion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (seleccionId: number) =>
      unwrap(
        api.DELETE("/api/v1/carrito/selecciones/{seleccion_id}", {
          params: { path: { seleccion_id: seleccionId } },
        }),
      ),
    onSuccess: (_, seleccionId) => sinSeleccion(queryClient, seleccionId),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: CARRITO_KEY });
    },
  });
}

/** Vacía el carrito; con el carrito ya vacío también responde 204. */
export function useVaciarCarrito() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/carrito")),
    onSuccess: () =>
      queryClient.setQueryData<Carrito>(CARRITO_KEY, { selecciones: [], cantidad: 0, total: 0 }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: CARRITO_KEY });
    },
  });
}
