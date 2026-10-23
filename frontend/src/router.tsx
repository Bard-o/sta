import { createBrowserRouter } from "react-router";
import { RequireRole, SoloRegistroPendiente, SoloVisitantes } from "@/auth/require-role";
import { RUTA_PRIMER_INGRESO } from "@/auth/roles";
import { AppLayout } from "@/layouts/app-layout";
import { AdministradoresPage } from "@/pages/administradores";
import { EditarVueloPage } from "@/pages/editar-vuelo";
import { InicioPage } from "@/pages/inicio";
import { InicioRolPage } from "@/pages/inicio-rol";
import { LoginPage } from "@/pages/login";
import { NoEncontradaPage } from "@/pages/no-encontrada";
import { NoticiasPage } from "@/pages/noticias";
import { BajaNoticiasPage } from "@/pages/noticias-baja";
import { NuevaPromocionPage } from "@/pages/nueva-promocion";
import { PerfilPage } from "@/pages/perfil";
import { PrimerIngresoPage } from "@/pages/primer-ingreso";
import { ProgramarVueloPage } from "@/pages/programar-vuelo";
import { PromocionesPage } from "@/pages/promociones";
import { RegistroPage } from "@/pages/registro";
import { RestablecerContrasenaPage } from "@/pages/restablecer-contrasena";
import { VerificarCorreoPage } from "@/pages/verificar-correo";
import { VueloDetallePage } from "@/pages/vuelo-detalle";
import { VuelosProgramadosPage } from "@/pages/vuelos-programados";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      // Públicas
      { path: "/", element: <InicioPage /> },
      { path: "/noticias", element: <NoticiasPage /> },
      { path: "/noticias/baja", element: <BajaNoticiasPage /> },
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
        element: <RequireRole roles={["cliente", "admin", "root"]} />,
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
          { path: "/admin/vuelos", element: <VuelosProgramadosPage /> },
          { path: "/admin/vuelos/nuevo", element: <ProgramarVueloPage /> },
          { path: "/admin/vuelos/:vueloId/editar", element: <EditarVueloPage /> },
          { path: "/admin/vuelos/:vueloId/promocion", element: <NuevaPromocionPage /> },
          { path: "/admin/promociones", element: <PromocionesPage /> },
        ],
      },
      {
        element: <RequireRole roles={["root"]} />,
        children: [
          { path: "/root", element: <InicioRolPage /> },
          { path: "/root/administradores", element: <AdministradoresPage /> },
        ],
      },

      { path: "*", element: <NoEncontradaPage /> },
    ],
  },
]);
