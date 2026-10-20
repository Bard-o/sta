import { Outlet, useNavigate } from "react-router";
import { toast } from "sonner";
import { NAV_ROL, NAV_VISITANTE, NOMBRE_ROL, INICIO_ROL } from "@/auth/roles";
import { useLogout, useSesion } from "@/auth/sesion";
import { Backdrop } from "@/components/ui/backdrop";
import { Button } from "@/components/ui/button";
import { Shell } from "@/components/ui/shell";
import { TopNav } from "@/components/ui/top-nav";

/** Backdrop + ventana + barra del rol. Todas las pantallas viven dentro de este layout. */
export function AppLayout() {
  const { data: usuario } = useSesion();
  const logout = useLogout();
  const navigate = useNavigate();

  const cerrarSesion = () =>
    logout.mutate(undefined, {
      onSuccess: () => {
        // HU-04: tras cerrar sesión se muestra la página pública de inicio.
        navigate("/", { replace: true });
        toast("Cerraste tu sesión.");
      },
      onError: (e) => toast.error(e.message),
    });

  const nav = usuario ? (
    <TopNav
      homeHref={INICIO_ROL[usuario.rol]}
      items={NAV_ROL[usuario.rol]}
      user={{ name: usuario.nombre_usuario, role: NOMBRE_ROL[usuario.rol] }}
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

  return (
    <Backdrop className="flex min-h-full flex-col">
      {/* Administrador y root no usan el chatbot (Apéndice B). */}
      <Shell nav={nav} chat={!usuario || usuario.rol === "cliente"}>
        <Outlet />
      </Shell>
    </Backdrop>
  );
}
