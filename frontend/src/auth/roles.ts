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

/** S07 · Primer ingreso del administrador (HU-12). La pantalla la construye su propio issue. */
export const RUTA_PRIMER_INGRESO = "/admin/primer-ingreso";

/** Un administrador que aún no completó su registro solo puede ver S07 (HU-12). `=== false` y no
 *  `!`: si el campo no viniera en la respuesta, no se trata a nadie como pendiente. */
export function registroPendiente(usuario: Usuario): boolean {
  return usuario.rol === "admin" && usuario.registro_completo === false;
}

/** Página de inicio del usuario: la de su rol, o S07 si tiene el registro pendiente. */
export function inicioDe(usuario: Usuario): string {
  return registroPendiente(usuario) ? RUTA_PRIMER_INGRESO : INICIO_ROL[usuario.rol];
}

/** Nombre para el menú: nombres y apellidos si los hay (el root y el administrador con el registro
 *  incompleto no los tienen), o el nombre de usuario. */
export function nombreVisible(usuario: Usuario): string {
  const nombre = [usuario.nombres, usuario.apellidos].filter(Boolean).join(" ");
  return nombre || usuario.nombre_usuario;
}

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

/** A dónde ir tras iniciar sesión: S07 si el registro está pendiente, `?next=` si es una ruta
 *  interna, o el inicio del rol. */
export function destinoTrasLogin(usuario: Usuario, next: string | null): string {
  if (registroPendiente(usuario)) return RUTA_PRIMER_INGRESO;
  if (next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\")) {
    return next;
  }
  return INICIO_ROL[usuario.rol];
}
