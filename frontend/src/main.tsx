import "@design/tokens.css";
import "@design/components.css";
import "./index.css";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { ApiError } from "@/api/client";
import { SESION_KEY } from "@/auth/sesion";
import { Toaster } from "@/components/ui/sonner";
import { router } from "@/router";

// RNF-14: si cualquier petición responde 401, la sesión venció; se olvida el usuario y las
// rutas protegidas llevan al login.
const alVencerSesion = (error: Error) => {
  if (error instanceof ApiError && error.status === 401) {
    queryClient.setQueryData(SESION_KEY, null);
  }
};

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: alVencerSesion }),
  mutationCache: new MutationCache({ onError: alVencerSesion }),
  defaultOptions: {
    queries: {
      retry: (intentos, error) =>
        !(error instanceof ApiError && error.status < 500) && intentos < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  </StrictMode>,
);
