import type { Schemas } from "@/api/client";
import type { Tone } from "@/components/ui/badge";

export type Noticia = Schemas["Noticia"];
export type ClaseVuelo = "economica" | "primera";

export const NOMBRE_CLASE: Record<ClaseVuelo, string> = {
  economica: "Económica",
  primera: "Primera",
};

/** ¿Se puede mostrar como vigente? El servidor ya lo indica en `vigente`; además, una promoción
 *  vencida, agotada o cancelada nunca se destaca (HU-19), venga como venga el dato. */
export function esVigente(n: Noticia): boolean {
  if (!n.vigente) return false;
  return n.tipo !== "promocion" || n.promocion?.estado === "vigente";
}

/** Etiqueta del estado de la noticia, siempre con palabra (el color nunca va solo). */
export function etiquetaDeNoticia(n: Noticia): { label: string; tone: Tone } | null {
  if (n.tipo === "promocion") {
    if (esVigente(n)) return { label: "Vigente", tone: "accent" };
    switch (n.promocion?.estado) {
      case "agotada":
        return { label: "Agotada", tone: "danger" };
      case "cancelada":
        return { label: "Cancelada", tone: "neutral" };
      case "programada":
        return { label: "Programada", tone: "info" };
      default:
        return { label: "Vencida", tone: "neutral" };
    }
  }
  return n.vigente ? null : { label: "Vuelo no disponible", tone: "neutral" };
}

export type PrecioNoticia = { clase: ClaseVuelo; anterior?: number; actual: number };

/** El precio que resume la noticia: el de la promoción vigente, con el anterior tachado, o el de
 *  económica del vuelo. */
export function precioDeNoticia(n: Noticia): PrecioNoticia {
  const p = n.promocion;
  if (p && esVigente(n)) {
    if (p.clases.includes("economica") && p.precio_economica !== null) {
      return { clase: "economica", anterior: n.precio_economica, actual: p.precio_economica };
    }
    if (p.precio_primera !== null) {
      return { clase: "primera", anterior: n.precio_primera, actual: p.precio_primera };
    }
  }
  return { clase: "economica", actual: n.precio_economica };
}
