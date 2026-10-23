// Datos de prueba de noticias y vuelos (HU-19), tipados con el contrato.
import type { Schemas } from "@/api/client";

type Noticia = Schemas["Noticia"];
type VueloDetalle = Schemas["VueloDetalle"];

export const BOGOTA = { codigo: "BOG", nombre: "Bogotá", zona_horaria: "America/Bogota" };
export const MIAMI = { codigo: "MIA", nombre: "Miami", zona_horaria: "America/New_York" };
export const MADRID = { codigo: "MAD", nombre: "Madrid", zona_horaria: "Europe/Madrid" };
export const PEREIRA = { codigo: "PEI", nombre: "Pereira", zona_horaria: "America/Bogota" };
export const CARTAGENA = { codigo: "CTG", nombre: "Cartagena", zona_horaria: "America/Bogota" };

/** Noticia de un vuelo nuevo y vigente; `cambios` ajusta lo que cada test necesita. */
export function noticia(id: number, cambios: Partial<Noticia> = {}): Noticia {
  return {
    id,
    tipo: "vuelo",
    titulo: `Nuevo vuelo Pereira → Cartagena ${id}`,
    publicada_en: "2026-10-01T15:00:00Z",
    vigente: true,
    vuelo_id: 100 + id,
    vuelo_codigo: `STA-${String(100 + id).padStart(5, "0")}`,
    origen: PEREIRA,
    destino: CARTAGENA,
    salida: "2026-11-20T14:15:00Z",
    precio_economica: 320000,
    precio_primera: 800000,
    imagen_url: "/imagenes/ciudades/CTG.jpg",
    promocion: null,
    ...cambios,
  };
}

/** Noticia de una promoción del 30 % en económica de Bogotá → Miami. */
export function noticiaPromocion(
  id: number,
  estado: "programada" | "vigente" | "vencida" | "agotada" | "cancelada" = "vigente",
  cambios: Partial<Noticia> = {},
): Noticia {
  return noticia(id, {
    tipo: "promocion",
    titulo: "Promoción del 30 % en Bogotá → Miami, económica",
    vigente: estado === "vigente",
    origen: BOGOTA,
    destino: MIAMI,
    salida: "2026-10-29T04:30:00Z",
    precio_economica: 1980000,
    precio_primera: 4500000,
    imagen_url: "/imagenes/ciudades/MIA.jpg",
    promocion: {
      porcentaje: 30,
      clases: ["economica"],
      inicio: "2026-10-18T13:00:00Z",
      fin: "2026-10-27T04:59:00Z",
      estado,
      precio_economica: 1386000,
      precio_primera: null,
    },
    ...cambios,
  });
}

export const pagina = (items: Noticia[], pag = 1, total = items.length, por = 10) => ({
  status: 200,
  body: { items, total, pagina: pag, por_pagina: por },
});

/** Bogotá → Madrid, 10 h de vuelo: llega al día siguiente y con otro desfase. */
export function vueloDetalle(cambios: Partial<VueloDetalle> = {}): VueloDetalle {
  return {
    id: 88,
    codigo: "STA-00088",
    tipo: "internacional",
    origen: BOGOTA,
    destino: MADRID,
    salida: "2026-12-11T03:00:00Z",
    llegada: "2026-12-11T13:00:00Z",
    duracion_minutos: 600,
    precio_economica: 2450000,
    precio_primera: 6900000,
    capacidad: { primera: 50, economica: 200, total: 250 },
    estado: "programado",
    economica: {
      precio_base: 2450000,
      precio_vigente: 2450000,
      promocion: null,
      disponibles: 120,
      agotada: false,
    },
    primera: {
      precio_base: 6900000,
      precio_vigente: 6900000,
      promocion: null,
      disponibles: 12,
      agotada: false,
    },
    ...cambios,
  };
}
