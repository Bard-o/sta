// Módulo noticias (HU-19): públicas y solo de lectura.
import { db, noticia, paginar } from "../estado";
import { http } from "../http";

const MAX_CARRUSEL = 10;

export const noticiasHandlers = [
  http.get("/api/v1/noticias", ({ query, response }) => {
    const items = db.noticias
      .map(noticia)
      .sort((a, b) => b.publicada_en.localeCompare(a.publicada_en));
    return response(200).json(paginar(items, query.get("pagina"), query.get("por_pagina"), 10));
  }),

  // Primero las promociones vigentes, luego los vuelos más recientes; cada vuelo una sola vez.
  http.get("/api/v1/noticias/carrusel", ({ response }) => {
    const vigentes = db.noticias
      .map(noticia)
      .filter((n) => n.vigente)
      .sort((a, b) => b.publicada_en.localeCompare(a.publicada_en));
    const promociones = vigentes.filter((n) => n.tipo === "promocion");
    const conPromocion = new Set(promociones.map((n) => n.vuelo_id));
    const vuelos = vigentes.filter((n) => n.tipo === "vuelo" && !conPromocion.has(n.vuelo_id));
    return response(200).json([...promociones, ...vuelos].slice(0, MAX_CARRUSEL));
  }),
];
