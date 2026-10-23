import type { Schemas } from "@/api/client";

export type Ciudad = Schemas["Ciudad"];
export type VueloAdmin = Schemas["VueloAdmin"];

export const ciudad = (
  codigo: string,
  nombre: string,
  tipo: "nacional" | "internacional" = "nacional",
  zona = "America/Bogota",
): Ciudad => ({
  codigo,
  nombre,
  pais: tipo === "nacional" ? "Colombia" : "Exterior",
  zona_horaria: zona,
  tipo,
  habilitada_internacional: ["BOG", "PEI", "MDE"].includes(codigo),
  imagen_url: `/imagenes/ciudades/${codigo}.jpg`,
});

export const PEI = ciudad("PEI", "Pereira");
export const BOG = ciudad("BOG", "Bogotá");
export const MDE = ciudad("MDE", "Medellín");

export const resumenCiudad = (c: Ciudad) => ({
  codigo: c.codigo,
  nombre: c.nombre,
  zona_horaria: c.zona_horaria,
});

const SIN_VENDER = { capacidad: 125, vendidas: 0, reservadas: 0, disponibles: 125 };

/** Pereira → Bogotá, 10/12/2026 06:00 (11:00Z), 50 min, sin ventas: editable y cancelable. */
export const vueloAdmin = (cambios: Partial<VueloAdmin> = {}): VueloAdmin => ({
  id: 31,
  codigo: "STA-00031",
  tipo: "nacional",
  origen: resumenCiudad(PEI),
  destino: resumenCiudad(BOG),
  salida: "2026-12-10T11:00:00Z",
  llegada: "2026-12-10T11:50:00Z",
  duracion_minutos: 50,
  precio_economica: 280000,
  precio_primera: 750000,
  capacidad: { primera: 25, economica: 125, total: 150 },
  estado: "programado",
  ocupacion: {
    primera: { capacidad: 25, vendidas: 0, reservadas: 0, disponibles: 25 },
    economica: SIN_VENDER,
  },
  reservas_activas: 0,
  tiquetes_vendidos: 0,
  editable: true,
  motivo_no_editable: null,
  cancelable: true,
  promociones: [],
  ...cambios,
});

/** Con 2 reservas activas (3 sillas): no se edita, sí se cancela. */
export const conReservas = (cambios: Partial<VueloAdmin> = {}) =>
  vueloAdmin({
    id: 51,
    codigo: "STA-00051",
    destino: resumenCiudad(MDE),
    salida: "2026-12-10T12:40:00Z",
    reservas_activas: 2,
    editable: false,
    motivo_no_editable: "Tiene 2 reservas activas.",
    ocupacion: {
      primera: { capacidad: 25, vendidas: 0, reservadas: 1, disponibles: 24 },
      economica: { capacidad: 125, vendidas: 0, reservadas: 2, disponibles: 123 },
    },
    ...cambios,
  });

/** Con tiquetes vendidos: ni se edita ni se cancela (solo por fuerza mayor). */
export const conTiquetes = (cambios: Partial<VueloAdmin> = {}) =>
  vueloAdmin({
    id: 88,
    codigo: "STA-00088",
    tiquetes_vendidos: 99,
    editable: false,
    motivo_no_editable: "Tiene compras de tiquetes.",
    cancelable: false,
    ...cambios,
  });

export const pagina = (items: VueloAdmin[], total = items.length, numero = 1) => ({
  status: 200,
  body: { items, total, pagina: numero, por_pagina: 10 },
});
