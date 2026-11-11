import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { toast } from "sonner";
import {
  inicioDe,
  NAV_ROL,
  NAV_VISITANTE,
  nombreVisible,
  NOMBRE_ROL,
} from "@/auth/roles";
import { usePerfil } from "@/auth/perfil";
import { useLogout, useSesion } from "@/auth/sesion";
import { RUTA_VERIFICACION } from "@/auth/verificacion";
import { Backdrop } from "@/components/ui/backdrop";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Shell } from "@/components/ui/shell";
import { TopNav } from "@/components/ui/top-nav";

/** Backdrop + ventana + barra del rol. Todas las pantallas viven dentro de este layout. */
export function AppLayout() {
  const { data: usuario, isPending } = useSesion();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  // El root no tiene perfil con imagen; los demás la muestran en la barra.
  const { data: perfil } = usePerfil(Boolean(usuario) && usuario?.rol !== "root");

  const cerrarSesion = () =>
    logout.mutate(undefined, {
      onSuccess: () => {
        // HU-04: tras cerrar sesión se muestra la página pública de inicio.
        navigate("/", { replace: true });
        toast("Cerraste tu sesión.");
      },
      onError: (e) => toast.error(e.message),
    });

  // Mientras se resuelve la sesión la barra queda neutra: así quien ya entró no ve un instante el
  // menú de visitante antes del de su rol.
  const nav = isPending ? (
    <TopNav />
  ) : usuario ? (
    <TopNav
      homeHref={inicioDe(usuario)}
      items={NAV_ROL[usuario.rol]}
      user={{
        name: nombreVisible(usuario),
        role: NOMBRE_ROL[usuario.rol],
        imageUrl: perfil?.imagen_url,
        // El root entra a /perfil solo para cambiar su contraseña (HU-06).
        href: "/perfil",
      }}
      right={
        <Button variant="ghost" size="sm" onClick={cerrarSesion} disabled={logout.isPending}>
          Cerrar sesión
        </Button>
      }
    />
  ) : (
    <TopNav
      items={NAV_VISITANTE}
      right={
        <>
          <Button variant="ghost" size="sm" href="/login">
            Iniciar sesión
          </Button>
          <Button variant="secondary" size="sm" href="/registro">
            Crear cuenta
          </Button>
        </>
      }
    />
  );

  // HU-02: un cliente con el correo sin verificar no puede reservar, comprar ni suscribirse.
  const avisarVerificacion =
    usuario?.rol === "cliente" &&
    !usuario.email_verificado &&
    location.pathname !== RUTA_VERIFICACION;

  return (
    <Backdrop className="flex min-h-full flex-col">
      {/* Administrador y root no usan el chatbot (Apéndice B). */}
      <Shell nav={nav} chat={!isPending && (!usuario || usuario.rol === "cliente")}>
        {avisarVerificacion && (
          <Notice tone="info">
            Verifica tu correo para reservar, comprar y suscribirte a noticias.{" "}
            <Link className="sta-link" to={RUTA_VERIFICACION}>
              Verificar correo
            </Link>
          </Notice>
        )}
        <Outlet />
      </Shell>
    </Backdrop>
  );
}
