import { createBrowserRouter } from "react-router";
import { RequireRole, SoloVisitantes } from "@/auth/require-role";
import { AppLayout } from "@/layouts/app-layout";
import { AdministradoresPage } from "@/pages/administradores";
import { BuscarPage } from "@/pages/buscar";
import { BuscarIdaYRegresoPage } from "@/pages/buscar-ida-y-regreso";
import { CarritoPage } from "@/pages/carrito";
import { CompletarRegistroPage } from "@/pages/completar-registro";
import { CompraPagoPage } from "@/pages/compra-pago";
import { CompraViajerosPage } from "@/pages/compra-viajeros";
import { EditarVueloPage } from "@/pages/editar-vuelo";
import { InicioPage } from "@/pages/inicio";
import { InicioRolPage } from "@/pages/inicio-rol";
import { LoginPage } from "@/pages/login";
import { MisViajesPage } from "@/pages/mis-viajes";
import { MonederoPage } from "@/pages/monedero";
import { NoEncontradaPage } from "@/pages/no-encontrada";
import { NoticiasPage } from "@/pages/noticias";
import { BajaNoticiasPage } from "@/pages/noticias-baja";
import { NuevaTarjetaPage } from "@/pages/nueva-tarjeta";
import { NuevaPromocionPage } from "@/pages/nueva-promocion";
import { PerfilPage } from "@/pages/perfil";
import { ProgramarVueloPage } from "@/pages/programar-vuelo";
import { PromocionesPage } from "@/pages/promociones";
import { RecargarMonederoPage } from "@/pages/recargar-monedero";
import { RegistroPage } from "@/pages/registro";
import { RestablecerContrasenaPage } from "@/pages/restablecer-contrasena";
import { VerificarCorreoPage } from "@/pages/verificar-correo";
import { VueloDetallePage } from "@/pages/vuelo-detalle";
import { VuelosProgramadosPage } from "@/pages/vuelos-programados";
import { VuelosRealizadosPage } from "@/pages/vuelos-realizados";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      // Públicas
      { path: "/", element: <InicioPage /> },
      { path: "/noticias", element: <NoticiasPage /> },
      { path: "/noticias/baja", element: <BajaNoticiasPage /> },
      { path: "/vuelos/:vueloId", element: <VueloDetallePage /> },
      // HU-20, HU-21: la búsqueda es pública (Apéndice B); agregar al carrito pide sesión.
      { path: "/buscar", element: <BuscarPage /> },
      { path: "/buscar/ida-y-regreso", element: <BuscarIdaYRegresoPage /> },
      { path: "/verificar-correo", element: <VerificarCorreoPage /> },
      { path: "/restablecer-contrasena", element: <RestablecerContrasenaPage /> },
      // HU-10 y HU-12: el enlace de la invitación llega sin sesión.
      { path: "/completar-registro", element: <CompletarRegistroPage /> },
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
        children: [
          { path: "/cliente", element: <InicioRolPage /> },
          // Iteración 2 (docs/api/iteracion-2.md, «Rutas del frontend»).
          { path: "/carrito", element: <CarritoPage /> },
          { path: "/compra/viajeros", element: <CompraViajerosPage /> },
          { path: "/compra/pago/:compraId", element: <CompraPagoPage /> },
          { path: "/mis-viajes", element: <MisViajesPage /> },
          { path: "/monedero", element: <MonederoPage /> },
          { path: "/monedero/tarjetas/nueva", element: <NuevaTarjetaPage /> },
          { path: "/monedero/recargar", element: <RecargarMonederoPage /> },
        ],
      },
      {
        element: <RequireRole roles={["cliente", "admin", "root"]} />,
        children: [{ path: "/perfil", element: <PerfilPage /> }],
      },
      {
        element: <RequireRole roles={["admin"]} />,
        children: [
          { path: "/admin", element: <InicioRolPage /> },
          { path: "/admin/vuelos", element: <VuelosProgramadosPage /> },
          { path: "/admin/vuelos/nuevo", element: <ProgramarVueloPage /> },
          { path: "/admin/vuelos/:vueloId/editar", element: <EditarVueloPage /> },
          { path: "/admin/vuelos/:vueloId/promocion", element: <NuevaPromocionPage /> },
          { path: "/admin/promociones", element: <PromocionesPage /> },
          { path: "/admin/vuelos-realizados", element: <VuelosRealizadosPage /> },
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
