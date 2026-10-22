import { createBrowserRouter } from "react-router";
import { RequireRole, SoloVisitantes } from "@/auth/require-role";
import { AppLayout } from "@/layouts/app-layout";
import { InicioPage } from "@/pages/inicio";
import { InicioRolPage } from "@/pages/inicio-rol";
import { LoginPage } from "@/pages/login";
import { NoEncontradaPage } from "@/pages/no-encontrada";
import { NoticiasPage } from "@/pages/noticias";
import { VueloDetallePage } from "@/pages/vuelo-detalle";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      // Públicas
      { path: "/", element: <InicioPage /> },
      { path: "/noticias", element: <NoticiasPage /> },
      { path: "/vuelos/:vueloId", element: <VueloDetallePage /> },
      { element: <SoloVisitantes />, children: [{ path: "/login", element: <LoginPage /> }] },

      // Protegidas por rol (RF-11). El servidor vuelve a validar cada petición (RNF-10).
      {
        element: <RequireRole roles={["cliente"]} />,
        children: [{ path: "/cliente", element: <InicioRolPage /> }],
      },
      {
        element: <RequireRole roles={["admin"]} />,
        children: [{ path: "/admin", element: <InicioRolPage /> }],
      },
      {
        element: <RequireRole roles={["root"]} />,
        children: [{ path: "/root", element: <InicioRolPage /> }],
      },

      { path: "*", element: <NoEncontradaPage /> },
    ],
  },
]);
