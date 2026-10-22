import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { crearQueryClient } from "@/auth/consultas";

/** Renderiza rutas en memoria con el QueryClient de la app (sin reintentos), para que el 401 de
 *  una sesión vencida se comporte como en producción. */
export function renderRutas(rutas: RouteObject[], url: string) {
  const queryClient = crearQueryClient({ reintentar: false });
  const router = createMemoryRouter(rutas, { initialEntries: [url] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, queryClient };
}
