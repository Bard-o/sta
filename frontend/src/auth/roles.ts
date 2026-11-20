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

/** Página de inicio del usuario: la de su rol (HU-03). */
export function inicioDe(usuario: Usuario): string {
  return INICIO_ROL[usuario.rol];
}

/** Nombre para el menú: nombres y apellidos si los hay (el root no los tiene), o el usuario. */
export function nombreVisible(usuario: Usuario): string {
  const nombre = [usuario.nombres, usuario.apellidos].filter(Boolean).join(" ");
  return nombre || usuario.nombre_usuario;
}

// Items del nav por rol (DESIGN.md › TopNav). Las rutas de la iteración 2 ya existen (router.tsx).
export const NAV_VISITANTE: NavItem[] = [
  { label: "Vuelos", icon: "plane", href: "/buscar" },
  { label: "Noticias", icon: "news", href: "/noticias" },
  { label: "Check-in", icon: "check-circle", href: "/check-in" },
];

export const NAV_ROL: Record<Rol, NavItem[]> = {
  cliente: [
    { label: "Vuelos", icon: "plane", href: "/buscar" },
    { label: "Noticias", icon: "news", href: "/noticias" },
    { label: "Mis viajes", icon: "ticket", href: "/mis-viajes" },
    { label: "Monedero", icon: "wallet", href: "/monedero" },
    { label: "Muro", icon: "message", href: "/muro" },
    { label: "Carrito", icon: "cart", href: "/carrito" },
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

/** Ruta interna segura: empieza por `/`, no por `//` y no lleva `\`, tabulador ni saltos de línea
 *  (contrato de la iteración 2). El navegador quita `\t`, `\n` y `\r` al resolver una URL y lee `\`
 *  como `/`, así que `/\t/sitio.example` o `/a\b` terminarían fuera de la aplicación. */
export function esRutaInterna(ruta: string | null | undefined): ruta is string {
  return !!ruta && ruta.startsWith("/") && !ruta.startsWith("//") && !/[\\\t\n\r]/.test(ruta);
}

/** A dónde ir tras iniciar sesión: `?next=` si es una ruta interna, o el inicio del rol. */
export function destinoTrasLogin(usuario: Usuario, next: string | null): string {
  if (esRutaInterna(next)) return next;
  return INICIO_ROL[usuario.rol];
}
