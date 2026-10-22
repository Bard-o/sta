import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { SESION_KEY, SESION_VENCIDA_KEY } from "./sesion";

/** QueryClient de la app. RNF-14: si cualquier petición responde 401, la sesión venció; se olvida
 *  el usuario y las rutas protegidas llevan al login. Si había una sesión abierta, el login avisa
 *  que venció (un visitante que se equivoca de contraseña también recibe 401 y no debe verlo). */
export function crearQueryClient({ reintentar = true }: { reintentar?: boolean } = {}) {
  const alVencerSesion = (error: Error) => {
    if (!(error instanceof ApiError && error.status === 401)) return;
    if (queryClient.getQueryData(SESION_KEY)) queryClient.setQueryData(SESION_VENCIDA_KEY, true);
    queryClient.setQueryData(SESION_KEY, null);
  };

  const queryClient = new QueryClient({
    queryCache: new QueryCache({ onError: alVencerSesion }),
    mutationCache: new MutationCache({ onError: alVencerSesion }),
    defaultOptions: {
      queries: {
        retry: reintentar
          ? (intentos, error) => !(error instanceof ApiError && error.status < 500) && intentos < 2
          : false,
      },
      mutations: { retry: false },
    },
  });
  return queryClient;
}
