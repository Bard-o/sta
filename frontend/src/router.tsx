import { createBrowserRouter } from "react-router";
import { RequireRole, SoloRegistroPendiente, SoloVisitantes } from "@/auth/require-role";
import { RUTA_PRIMER_INGRESO } from "@/auth/roles";
import { AppLayout } from "@/layouts/app-layout";
import { InicioPage } from "@/pages/inicio";
import { InicioRolPage } from "@/pages/inicio-rol";
import { LoginPage } from "@/pages/login";
import { NoEncontradaPage } from "@/pages/no-encontrada";
import { PrimerIngresoPage } from "@/pages/primer-ingreso";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      // Públicas
      { path: "/", element: <InicioPage /> },
      { element: <SoloVisitantes />, children: [{ path: "/login", element: <LoginPage /> }] },

      // Protegidas por rol (RF-11). El servidor vuelve a validar cada petición (RNF-10).
      {
        element: <RequireRole roles={["cliente"]} />,
        children: [{ path: "/cliente", element: <InicioRolPage /> }],
      },
      {
        element: <RequireRole roles={["admin"]} />,
        children: [
          // HU-12: con el registro pendiente solo se puede ver S07.
          {
            element: <SoloRegistroPendiente />,
            children: [{ path: RUTA_PRIMER_INGRESO, element: <PrimerIngresoPage /> }],
          },
          { path: "/admin", element: <InicioRolPage /> },
        ],
      },
      {
        element: <RequireRole roles={["root"]} />,
        children: [{ path: "/root", element: <InicioRolPage /> }],
      },

      { path: "*", element: <NoEncontradaPage /> },
    ],
  },
]);
