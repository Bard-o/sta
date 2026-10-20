// Estado en memoria de la API simulada: lo que se crea o cambia dura hasta recargar la página
// (la sesión sí sobrevive a la recarga, en sessionStorage).
import { HttpResponse } from "msw";
import type { Schemas } from "@/api/client";
import { ADMINISTRADORES, CUENTAS, ciudad, precioConDescuento, PROMOCIONES, VUELOS } from "./datos";

type Usuario = Schemas["UsuarioSalida"];
type Rol = Usuario["rol"];
type Noticia = Schemas["Noticia"];
type VueloAdmin = Schemas["VueloAdmin"];

type NoticiaGuardada = {
  id: number;
  tipo: Noticia["tipo"];
  vuelo_id: number;
  promocion_id?: number;
  publicada_en: string;
};

export const db = {
  cuentas: structuredClone(CUENTAS),
  administradores: structuredClone(ADMINISTRADORES),
  vuelos: structuredClone(VUELOS),
  promociones: structuredClone(PROMOCIONES),
  noticias: [
    { id: 1, tipo: "vuelo", vuelo_id: 44, publicada_en: "2026-09-20T15:00:00Z" },
    { id: 2, tipo: "vuelo", vuelo_id: 90, publicada_en: "2026-09-27T17:30:00Z" },
    { id: 3, tipo: "vuelo", vuelo_id: 31, publicada_en: "2026-09-28T13:10:00Z" },
    {
      id: 4,
      tipo: "promocion",
      vuelo_id: 31,
      promocion_id: 3,
      publicada_en: "2026-09-30T20:10:00Z",
    },
    { id: 5, tipo: "vuelo", vuelo_id: 51, publicada_en: "2026-10-02T14:00:00Z" },
    { id: 6, tipo: "vuelo", vuelo_id: 76, publicada_en: "2026-10-05T16:20:00Z" },
    { id: 7, tipo: "vuelo", vuelo_id: 88, publicada_en: "2026-10-08T19:45:00Z" },
    {
      id: 8,
      tipo: "promocion",
      vuelo_id: 76,
      promocion_id: 1,
      publicada_en: "2026-10-18T14:12:00Z",
    },
    {
      id: 9,
      tipo: "promocion",
      vuelo_id: 88,
      promocion_id: 2,
      publicada_en: "2026-10-19T16:40:00Z",
    },
    { id: 10, tipo: "vuelo", vuelo_id: 92, publicada_en: "2026-10-19T21:40:00Z" },
  ] as NoticiaGuardada[],
};

let siguienteId = 1000;
export const nuevoId = () => ++siguienteId;

// ---------- Sesión ----------

const CLAVE_SESION = "sta-mock-sesion";

export const sesion = {
  get(): Usuario | null {
    try {
      const guardada = sessionStorage.getItem(CLAVE_SESION);
      return guardada ? (JSON.parse(guardada) as Usuario) : null;
    } catch {
      return null;
    }
  },
  set(usuario: Usuario | null) {
    try {
      if (usuario) sessionStorage.setItem(CLAVE_SESION, JSON.stringify(usuario));
      else sessionStorage.removeItem(CLAVE_SESION);
    } catch {
      // Sin sessionStorage la sesión simplemente no sobrevive a la recarga.
    }
  },
};

// ---------- Respuestas ----------

/** Error con el formato único de la API. */
export function error(
  status: number,
  codigo: string,
  mensaje: string,
  campos?: Record<string, string>,
  headers?: Record<string, string>,
) {
  return HttpResponse.json(
    { error: campos ? { codigo, mensaje, campos } : { codigo, mensaje } },
    { status, headers },
  );
}

/** Igual que require_role del backend: 401 sin sesión y 403 con otro rol. Un administrador
 *  con el registro incompleto solo pasa donde `registroIncompleto` lo permite (HU-12). */
export function exigirRol(roles: Rol[], { registroIncompleto = false } = {}) {
  const usuario = sesion.get();
  if (!usuario) return error(401, "no_autenticado", "Inicia sesión para continuar.");
  if (!roles.includes(usuario.rol)) {
    return error(403, "sin_permiso", "Tu rol no tiene permiso para esta acción.");
  }
  if (!usuario.registro_completo && !registroIncompleto) {
    return error(403, "registro_incompleto", "Completa tu registro para continuar.");
  }
  return undefined;
}

export function paginar<T>(
  items: T[],
  pagina: string | null,
  porPagina: string | null,
  defecto = 20,
) {
  const p = Math.max(1, Number(pagina ?? 1));
  const n = Math.max(1, Number(porPagina ?? defecto));
  return { items: items.slice((p - 1) * n, p * n), total: items.length, pagina: p, por_pagina: n };
}

// ---------- Vistas derivadas ----------

const NOMBRE_CLASE = { economica: "económica", primera: "primera" } as const;

export function vueloDetalle(v: VueloAdmin): Schemas["VueloDetalle"] {
  const vigente = (clase: "economica" | "primera") =>
    v.promociones.find((p) => p.estado === "vigente" && p.clases.includes(clase)) ?? null;
  const clase = (c: "economica" | "primera"): Schemas["ClaseDetalle"] => {
    const promocion = vigente(c);
    const base = c === "economica" ? v.precio_economica : v.precio_primera;
    const disponibles = v.ocupacion[c].disponibles;
    return {
      precio_base: base,
      precio_vigente: promocion ? precioConDescuento(base, promocion.porcentaje) : base,
      promocion,
      disponibles,
      agotada: disponibles === 0,
    };
  };
  return { ...vueloBase(v), economica: clase("economica"), primera: clase("primera") };
}

/** Solo los campos de Vuelo (sin los datos del administrador). */
export function vueloBase(v: VueloAdmin): Schemas["Vuelo"] {
  return {
    id: v.id,
    codigo: v.codigo,
    tipo: v.tipo,
    origen: v.origen,
    destino: v.destino,
    salida: v.salida,
    llegada: v.llegada,
    duracion_minutos: v.duracion_minutos,
    precio_economica: v.precio_economica,
    precio_primera: v.precio_primera,
    capacidad: v.capacidad,
    estado: v.estado,
  };
}

/** Promociones vigentes y programadas del vuelo, como las trae VueloAdmin. */
export function conPromociones(v: VueloAdmin): VueloAdmin {
  return {
    ...v,
    promociones: db.promociones
      .filter((p) => p.vuelo_id === v.id && (p.estado === "vigente" || p.estado === "programada"))
      .map(({ id, porcentaje, clases, inicio, fin, estado }) => ({
        id,
        porcentaje,
        clases,
        inicio,
        fin,
        estado,
      })),
  };
}

export function noticia(n: NoticiaGuardada): Noticia {
  const v = db.vuelos.find((x) => x.id === n.vuelo_id)!;
  const p = n.promocion_id ? db.promociones.find((x) => x.id === n.promocion_id) : undefined;
  const ruta = `${v.origen.nombre} → ${v.destino.nombre}`;
  const clases = p?.clases.map((c) => NOMBRE_CLASE[c]).join(" y ");
  return {
    id: n.id,
    tipo: n.tipo,
    titulo: p ? `Promoción del ${p.porcentaje} % en ${ruta}, ${clases}` : `Nuevo vuelo ${ruta}`,
    publicada_en: n.publicada_en,
    vigente: v.estado === "programado" && (!p || p.estado === "vigente"),
    vuelo_id: v.id,
    vuelo_codigo: v.codigo,
    origen: v.origen,
    destino: v.destino,
    salida: v.salida,
    precio_economica: v.precio_economica,
    precio_primera: v.precio_primera,
    imagen_url: ciudad(v.destino.codigo)?.imagen_url ?? "",
    promocion: p
      ? {
          porcentaje: p.porcentaje,
          clases: p.clases,
          inicio: p.inicio,
          fin: p.fin,
          estado: p.estado,
          precio_economica: p.clases.includes("economica")
            ? precioConDescuento(v.precio_economica, p.porcentaje)
            : null,
          precio_primera: p.clases.includes("primera")
            ? precioConDescuento(v.precio_primera, p.porcentaje)
            : null,
        }
      : null,
  };
}

export function publicarNoticia(tipo: Noticia["tipo"], vuelo_id: number, promocion_id?: number) {
  db.noticias.push({
    id: nuevoId(),
    tipo,
    vuelo_id,
    promocion_id,
    publicada_en: new Date().toISOString(),
  });
}
