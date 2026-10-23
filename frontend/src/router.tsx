import { createBrowserRouter } from "react-router";
import { RequireRole, SoloRegistroPendiente, SoloVisitantes } from "@/auth/require-role";
import { RUTA_PRIMER_INGRESO } from "@/auth/roles";
import { AppLayout } from "@/layouts/app-layout";
import { InicioPage } from "@/pages/inicio";
import { InicioRolPage } from "@/pages/inicio-rol";
import { LoginPage } from "@/pages/login";
import { NoEncontradaPage } from "@/pages/no-encontrada";
import { NoticiasPage } from "@/pages/noticias";
import { PerfilPage } from "@/pages/perfil";
import { PrimerIngresoPage } from "@/pages/primer-ingreso";
import { RegistroPage } from "@/pages/registro";
import { RestablecerContrasenaPage } from "@/pages/restablecer-contrasena";
import { VerificarCorreoPage } from "@/pages/verificar-correo";
import { VueloDetallePage } from "@/pages/vuelo-detalle";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      // Públicas
      { path: "/", element: <InicioPage /> },
      { path: "/noticias", element: <NoticiasPage /> },
      { path: "/vuelos/:vueloId", element: <VueloDetallePage /> },
      { path: "/verificar-correo", element: <VerificarCorreoPage /> },
      { path: "/restablecer-contrasena", element: <RestablecerContrasenaPage /> },
      {
        element: <SoloVisitantes />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/registro", element: <RegistroPage /> },
        ],
      },

      // Protegidas por rol (RF-11). El servidor vuelve a validar cada petición (RNF-10).
      {
        element: <RequireRole roles={["cliente"]} />,
        children: [{ path: "/cliente", element: <InicioRolPage /> }],
      },
      {
        element: <RequireRole roles={["cliente", "admin"]} />,
        children: [{ path: "/perfil", element: <PerfilPage /> }],
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
