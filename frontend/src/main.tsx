import "@design/tokens.css";
import "@design/components.css";
import "./index.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { crearQueryClient } from "@/auth/consultas";
import { Toaster } from "@/components/ui/sonner";
import { router } from "@/router";

const queryClient = crearQueryClient();

// VITE_API_MOCK=true: la API la responde MSW con datos de ejemplo (src/mocks), para avanzar en
// pantallas cuyo endpoint todavía es un stub (501). Solo en desarrollo.
async function prepararApiSimulada() {
  if (!import.meta.env.DEV || import.meta.env.VITE_API_MOCK !== "true") return;
  const { worker } = await import("@/mocks/browser");
  await worker.start({ onUnhandledFrame: "bypass" });
}

void prepararApiSimulada()
  .catch((e: unknown) => console.error("No se pudo activar la API simulada; se usa la real.", e))
  .then(() =>
    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <Toaster />
        </QueryClientProvider>
      </StrictMode>,
    ),
  );
