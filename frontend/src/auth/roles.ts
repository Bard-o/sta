import type { Schemas } from "@/api/client";
import type { NavItem } from "@/components/ui/top-nav";

export type Usuario = Schemas["UsuarioSalida"];
export type Rol = Usuario["rol"];

export const NOMBRE_ROL: Record<Rol, string> = {
  cliente: "Cliente",
  admin: "Administrador",
  root: "Root",
};

/** Página de inicio de cada rol (HU-03: tras iniciar sesión, el usuario entra a la suya). */
export const INICIO_ROL: Record<Rol, string> = {
  cliente: "/cliente",
  admin: "/admin",
  root: "/root",
};

// Items del nav por rol (DESIGN.md › TopNav). Las rutas se implementan en sus issues.
export const NAV_VISITANTE: NavItem[] = [
  { label: "Vuelos", icon: "plane", href: "/vuelos" },
  { label: "Noticias", icon: "news", href: "/noticias" },
  { label: "Check-in", icon: "check-circle", href: "/check-in" },
];

export const NAV_ROL: Record<Rol, NavItem[]> = {
  cliente: [
    { label: "Vuelos", icon: "plane", href: "/vuelos" },
    { label: "Noticias", icon: "news", href: "/noticias" },
    { label: "Mis viajes", icon: "ticket", href: "/mis-viajes" },
    { label: "Monedero", icon: "wallet", href: "/monedero" },
    { label: "Muro", icon: "message", href: "/muro" },
  ],
  admin: [
    { label: "Vuelos programados", icon: "plane", href: "/admin/vuelos" },
    { label: "Promociones", icon: "tag", href: "/admin/promociones" },
    { label: "Vuelos realizados", icon: "check-circle", href: "/admin/vuelos-realizados" },
    { label: "Muros", icon: "message", href: "/admin/muros" },
    { label: "Auditoría", icon: "list", href: "/admin/auditoria" },
  ],
  root: [
    { label: "Administradores", icon: "user", href: "/root/administradores" },
    { label: "Auditoría", icon: "list", href: "/root/auditoria" },
  ],
};

/** A dónde ir tras iniciar sesión: `?next=` si es una ruta interna, o el inicio del rol. */
export function destinoTrasLogin(rol: Rol, next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\")) {
    return next;
  }
  return INICIO_ROL[rol];
}
