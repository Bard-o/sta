import { Navigate, Outlet, useLocation, useSearchParams } from "react-router";
import { destinoTrasLogin, inicioDe, registroPendiente, type Rol } from "./roles";
import { useSesion } from "./sesion";

/** Rutas protegidas: sin sesión lleva al login; con otro rol, a la página de inicio de su rol.
 *  Es solo comodidad de la interfaz: el control real lo hace el servidor (RNF-10). */
export function RequireRole({ roles }: { roles: Rol[] }) {
  const { data: usuario, isPending } = useSesion();
  const location = useLocation();

  if (isPending) return null;
  if (!usuario) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (!roles.includes(usuario.rol)) return <Navigate to={inicioDe(usuario)} replace />;
  return <Outlet />;
}

/** S07: solo el administrador con el registro pendiente ve el formulario (HU-12). Uno que ya lo
 *  completó vuelve al inicio de su rol. */
export function SoloRegistroPendiente() {
  const { data: usuario, isPending } = useSesion();

  if (isPending) return null;
  if (!usuario) return <Navigate to="/login" replace />;
  if (!registroPendiente(usuario)) return <Navigate to={inicioDe(usuario)} replace />;
  return <Outlet />;
}

/** Rutas solo para visitantes (login, registro). Con sesión, lleva a `?next=` o al inicio del
 *  rol; así, al iniciar sesión basta con actualizar la sesión y esta ruta hace la redirección. */
export function SoloVisitantes() {
  const { data: usuario, isPending } = useSesion();
  const [params] = useSearchParams();
  if (isPending) return null;
  if (usuario) return <Navigate to={destinoTrasLogin(usuario, params.get("next"))} replace />;
  return <Outlet />;
}
