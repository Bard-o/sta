// Módulo búsqueda (HU-20, HU-21). Público. Solo aparecen vuelos programados antes de su límite
// de venta. Rangos invertidos → rango_invalido; una ida inexistente o fuera de venta → 404.
import type { Schemas } from "@/api/client";
import { conPromociones, db, error, paginar, vueloDetalle } from "../estado";
import { http } from "../http";
import { aLaVenta, type Clase, fechaLocal, horaLocal } from "../reglas";

type VueloAdmin = Schemas["VueloAdmin"];
type VueloBusqueda = Schemas["VueloBusqueda"];

function aBusqueda(v: VueloAdmin): VueloBusqueda {
  const detalle = vueloDetalle(conPromociones(v));
  const clase = (c: Clase): Schemas["ClaseBusqueda"] => {
    const d = detalle[c];
    const promocion = d.promocion;
    return {
      precio_base: d.precio_base,
      precio_vigente: d.precio_vigente,
      promocion: promocion ? { porcentaje: promocion.porcentaje, fin: promocion.fin } : null,
      disponibles: d.disponibles,
      agotada: d.agotada,
    };
  };
  const economica = clase("economica");
  const primera = clase("primera");
  return {
    id: v.id,
    codigo: v.codigo,
    tipo: v.tipo,
    origen: v.origen,
    destino: v.destino,
    salida: v.salida,
    llegada: v.llegada,
    duracion_minutos: v.duracion_minutos,
    economica,
    primera,
    agotado: economica.agotada && primera.agotada,
  };
}

const precioDe = (v: VueloBusqueda, clase: Clase | null) =>
  clase ? v[clase].precio_vigente : Math.min(v.economica.precio_vigente, v.primera.precio_vigente);

function ordenar(items: VueloBusqueda[], orden: string | null, clase: Clase | null) {
  const clave = (v: VueloBusqueda) =>
    orden === "fecha"
      ? Date.parse(v.salida)
      : orden === "duracion"
        ? v.duracion_minutos
        : precioDe(v, clase);
  return items.sort(
    (a, b) => clave(a) - clave(b) || a.salida.localeCompare(b.salida) || a.id - b.id,
  );
}

/** HU-20: cada rango invertido marca su extremo final. */
function validarRangos(q: URLSearchParams): Response | undefined {
  const campos: Record<string, string> = {};
  const numero = (k: string) => (q.get(k) === null ? null : Number(q.get(k)));
  const [pMin, pMax] = [numero("precio_min"), numero("precio_max")];
  if (pMin !== null && pMax !== null && pMin > pMax) {
    campos.precio_max = "Debe ser mayor o igual que el precio mínimo.";
  }
  const [fDesde, fHasta] = [q.get("fecha_desde"), q.get("fecha_hasta")];
  if (fDesde && fHasta && fHasta < fDesde) {
    campos.fecha_hasta = "La fecha final no puede ser anterior a la inicial.";
  }
  const [hDesde, hHasta] = [q.get("hora_desde"), q.get("hora_hasta")];
  if (hDesde && hHasta && hHasta.slice(0, 5) < hDesde.slice(0, 5)) {
    campos.hora_hasta = "La hora final no puede ser anterior a la inicial.";
  }
  const [dMin, dMax] = [numero("duracion_min"), numero("duracion_max")];
  if (dMin !== null && dMax !== null && dMin > dMax) {
    campos.duracion_max = "Debe ser mayor o igual que la duración mínima.";
  }
  if (Object.keys(campos).length === 0) return undefined;
  return error(422, "rango_invalido", "Revisa los rangos marcados.", campos);
}

export const busquedaHandlers = [
  http.get("/api/v1/busqueda/vuelos", ({ request, response }) => {
    const q = new URL(request.url).searchParams;
    const rango = validarRangos(q);
    if (rango) return response.untyped(rango);
    const clase = q.get("clase") as Clase | null;
    const codigo = q.get("codigo")?.toLowerCase();
    const numero = (k: string) => (q.get(k) === null ? null : Number(q.get(k)));
    const items = db.vuelos
      .filter((v) => aLaVenta(v))
      .filter((v) => !codigo || v.codigo.toLowerCase().includes(codigo))
      .filter((v) => !q.get("origen") || v.origen.codigo === q.get("origen"))
      .filter((v) => !q.get("destino") || v.destino.codigo === q.get("destino"))
      .filter((v) => !q.get("tipo") || v.tipo === q.get("tipo"))
      .filter((v) => {
        const dia = fechaLocal(v.salida, v.origen.zona_horaria);
        const hora = horaLocal(v.salida, v.origen.zona_horaria);
        const fd = q.get("fecha_desde");
        const fh = q.get("fecha_hasta");
        const hd = q.get("hora_desde")?.slice(0, 5);
        const hh = q.get("hora_hasta")?.slice(0, 5);
        return (
          (!fd || dia >= fd) && (!fh || dia <= fh) && (!hd || hora >= hd) && (!hh || hora <= hh)
        );
      })
      .filter((v) => {
        const [dMin, dMax] = [numero("duracion_min"), numero("duracion_max")];
        return (
          (dMin === null || v.duracion_minutos >= dMin) &&
          (dMax === null || v.duracion_minutos <= dMax)
        );
      })
      .map(aBusqueda)
      .filter((v) => {
        const [pMin, pMax] = [numero("precio_min"), numero("precio_max")];
        const precio = precioDe(v, clase);
        return (pMin === null || precio >= pMin) && (pMax === null || precio <= pMax);
      });
    return response(200).json(
      paginar(ordenar(items, q.get("orden"), clase), q.get("pagina"), q.get("por_pagina")),
    );
  }),

  // STA-00101 llega 14:30 a Nueva York: STA-00133 (20:00) sí es regreso el 15/04; STA-00129 (06:30) no.
  http.get("/api/v1/busqueda/regresos", ({ request, response }) => {
    const q = new URL(request.url).searchParams;
    const ida = db.vuelos.find((v) => v.id === Number(q.get("vuelo_ida_id")));
    if (!ida || !aLaVenta(ida)) {
      return response.untyped(
        error(404, "no_encontrado", "El vuelo de ida no existe o ya no está a la venta."),
      );
    }
    const fecha = q.get("fecha") ?? "";
    if (fecha < fechaLocal(ida.salida, ida.origen.zona_horaria)) {
      return response.untyped(
        error(422, "rango_invalido", "Revisa los rangos marcados.", {
          fecha: "La fecha de regreso no puede ser anterior a la de ida.",
        }),
      );
    }
    const clase = q.get("clase") as Clase | null;
    const items = db.vuelos
      .filter((v) => aLaVenta(v))
      .filter(
        (v) => v.origen.codigo === ida.destino.codigo && v.destino.codigo === q.get("destino"),
      )
      .filter((v) => fechaLocal(v.salida, v.origen.zona_horaria) === fecha)
      .filter((v) => Date.parse(v.salida) > Date.parse(ida.llegada))
      .map(aBusqueda);
    return response(200).json(
      paginar(ordenar(items, q.get("orden"), clase), q.get("pagina"), q.get("por_pagina")),
    );
  }),
];
