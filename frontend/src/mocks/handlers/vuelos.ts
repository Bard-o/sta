// Módulo vuelos (HU-13 a HU-18). Las reglas se simulan lo justo para ver cada estado de las
// pantallas: ruta no permitida, vuelo duplicado, vuelo con reservas o con tiquetes vendidos.
import type { Schemas } from "@/api/client";
import {
  armarVuelo,
  capacidad,
  CIUDADES,
  ciudad,
  PASAJEROS,
  resumenCiudad,
  tipoDeRuta,
} from "../datos";
import {
  conPromociones,
  db,
  error,
  exigirRol,
  nuevoId,
  paginar,
  publicarNoticia,
  vueloBase,
  vueloDetalle,
} from "../estado";
import { http } from "../http";
import { aIso, fechasEntre, localAUtc, sumarMinutos } from "../tiempo";

type VueloEntrada = Schemas["VueloEntrada"];
type Ciudad = Schemas["Ciudad"];

const DIAS: Schemas["SerieVuelosEntrada"]["dias_semana"] = [
  "dom",
  "lun",
  "mar",
  "mie",
  "jue",
  "vie",
  "sab",
];

const noEncontrado = () => error(404, "no_encontrado", "El vuelo no existe.");
const cerrado = () =>
  error(409, "vuelo_cerrado", "El vuelo ya salió, se realizó o está cancelado.");

/** RF-13, RF-14: devuelve las ciudades o el error de validación. */
function validarRuta(origen: string, destino: string): [Ciudad, Ciudad] | Response {
  const o = ciudad(origen);
  const d = ciudad(destino);
  if (!o || !d) {
    return error(422, "datos_invalidos", "Revisa los campos marcados.", {
      [o ? "destino" : "origen"]: "No es una ciudad del catálogo.",
    });
  }
  if (o.codigo === d.codigo) {
    return error(422, "datos_invalidos", "Revisa los campos marcados.", {
      destino: "El destino debe ser distinto del origen.",
    });
  }
  const internacional = o.tipo === "internacional" || d.tipo === "internacional";
  const permitida =
    !internacional ||
    (o.habilitada_internacional && d.tipo === "internacional") ||
    (d.habilitada_internacional && o.tipo === "internacional");
  if (!permitida) {
    return error(422, "ruta_no_permitida", "Esta ruta no está permitida.", {
      destino: "Las rutas internacionales salen de Pereira, Bogotá, Medellín, Cali o Cartagena.",
    });
  }
  return [o, d];
}

function salidaUtc(o: Ciudad, fecha: string, hora: string) {
  return aIso(localAUtc(fecha, hora.slice(0, 5), o.zona_horaria));
}

function duplicado(origen: string, destino: string, salida: string, excepto?: number) {
  return db.vuelos.some(
    (v) =>
      v.id !== excepto &&
      v.estado === "programado" &&
      v.origen.codigo === origen &&
      v.destino.codigo === destino &&
      v.salida === salida,
  );
}

function vistaPrevia(
  o: Ciudad,
  d: Ciudad,
  salida: string,
  duracion: number,
): Schemas["VueloVistaPrevia"] {
  const tipo = tipoDeRuta(o, d);
  return {
    tipo,
    origen: resumenCiudad(o),
    destino: resumenCiudad(d),
    salida,
    llegada: aIso(sumarMinutos(new Date(salida), duracion)),
    duracion_minutos: duracion,
    capacidad: capacidad(tipo),
  };
}

/** Valida un vuelo nuevo o editado; devuelve la salida en UTC o el error. */
function validarVuelo(datos: VueloEntrada, excepto?: number): [Ciudad, Ciudad, string] | Response {
  const ruta = validarRuta(datos.origen, datos.destino);
  if (ruta instanceof Response) return ruta;
  const salida = salidaUtc(ruta[0], datos.fecha_salida, datos.hora_salida);
  if (Date.parse(salida) <= Date.now()) {
    return error(422, "datos_invalidos", "Revisa los campos marcados.", {
      fecha_salida: "La salida debe ser en el futuro.",
    });
  }
  if (duplicado(datos.origen, datos.destino, salida, excepto)) {
    return error(409, "vuelo_duplicado", "Ya existe un vuelo de esta ruta a esa hora.", {
      hora_salida: "Ya existe un vuelo de esta ruta a esa hora.",
    });
  }
  return [...ruta, salida];
}

function serie(datos: Schemas["SerieVuelosEntrada"]) {
  const ruta = validarRuta(datos.origen, datos.destino);
  if (ruta instanceof Response) return ruta;
  const fechas: string[] = [];
  const omitidas: Schemas["FechaOmitida"][] = [];
  for (const fecha of fechasEntre(datos.desde, datos.hasta)) {
    if (!datos.dias_semana.includes(DIAS[new Date(`${fecha}T12:00:00Z`).getUTCDay()])) continue;
    const salida = salidaUtc(ruta[0], fecha, datos.hora_salida);
    if (Date.parse(salida) <= Date.now()) {
      omitidas.push({ fecha, codigo: "salida_en_pasado", motivo: "La salida ya pasó." });
    } else if (duplicado(datos.origen, datos.destino, salida)) {
      omitidas.push({ fecha, codigo: "vuelo_duplicado", motivo: "Ya existe un vuelo igual." });
    } else {
      fechas.push(fecha);
    }
  }
  return { ruta, fechas, omitidas };
}

function crear(o: Ciudad, d: Ciudad, salida: string, datos: Omit<VueloEntrada, "fecha_salida">) {
  const id = Math.max(...db.vuelos.map((v) => v.id)) + 1;
  const vuelo = armarVuelo(id, o.codigo, d.codigo, salida, datos.duracion_minutos, [
    datos.precio_economica,
    datos.precio_primera,
  ]);
  db.vuelos.push(vuelo);
  publicarNoticia("vuelo", id); // RF-22
  return vuelo;
}

export const vuelosHandlers = [
  http.get("/api/v1/ciudades", ({ response }) => response(200).json(CIUDADES)),

  // ?estado=programado|realizado|cancelado&q=código o ciudad
  http.get("/api/v1/vuelos", ({ query, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const estado = query.get("estado") ?? "programado";
    const q = query.get("q")?.toLowerCase();
    const items = db.vuelos
      .filter((v) => v.estado === estado)
      .filter(
        (v) =>
          !q ||
          v.codigo.toLowerCase().includes(q) ||
          v.origen.nombre.toLowerCase().includes(q) ||
          v.destino.nombre.toLowerCase().includes(q),
      )
      .sort((a, b) =>
        estado === "programado"
          ? a.salida.localeCompare(b.salida)
          : b.salida.localeCompare(a.salida),
      )
      .map(conPromociones);
    return response(200).json(paginar(items, query.get("pagina"), query.get("por_pagina")));
  }),

  // Ruta no permitida (p. ej. MZL → MIA), salida pasada o un vuelo igual → errores de HU-13.
  http.post("/api/v1/vuelos", async ({ request, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const validado = validarVuelo(datos);
    if (validado instanceof Response) return response.untyped(validado);
    return response(201).json(crear(...validado, datos));
  }),

  http.post("/api/v1/vuelos/vista-previa", async ({ request, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const validado = validarVuelo(datos);
    if (validado instanceof Response) return response.untyped(validado);
    return response(200).json(vistaPrevia(...validado, datos.duracion_minutos));
  }),

  http.post("/api/v1/vuelos/recurrentes", async ({ request, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const resultado = serie(datos);
    if (resultado instanceof Response) return response.untyped(resultado);
    const [o, d] = resultado.ruta;
    const creados = resultado.fechas.map((fecha) =>
      vueloBase(crear(o, d, salidaUtc(o, fecha, datos.hora_salida), datos)),
    );
    return response(201).json({ creados, omitidas: resultado.omitidas });
  }),

  http.post("/api/v1/vuelos/recurrentes/vista-previa", async ({ request, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const resultado = serie(datos);
    if (resultado instanceof Response) return response.untyped(resultado);
    const tipo = tipoDeRuta(...resultado.ruta);
    return response(200).json({
      tipo,
      capacidad: capacidad(tipo),
      fechas: resultado.fechas,
      omitidas: resultado.omitidas,
    });
  }),

  // Público: lo abren las noticias y el carrusel (HU-19).
  http.get("/api/v1/vuelos/{vuelo_id}", ({ params, response }) => {
    const vuelo = db.vuelos.find((v) => v.id === Number(params.vuelo_id));
    if (!vuelo) return response.untyped(noEncontrado());
    return response(200).json(vueloDetalle(conPromociones(vuelo)));
  }),

  http.get("/api/v1/vuelos/{vuelo_id}/gestion", ({ params, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const vuelo = db.vuelos.find((v) => v.id === Number(params.vuelo_id));
    if (!vuelo) return response.untyped(noEncontrado());
    return response(200).json(conPromociones(vuelo));
  }),

  // STA-00051 (reservas) y STA-00088 (ventas) → vuelo_con_reservas.
  http.put("/api/v1/vuelos/{vuelo_id}", async ({ params, request, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const indice = db.vuelos.findIndex((v) => v.id === Number(params.vuelo_id));
    const actual = db.vuelos[indice];
    if (!actual) return response.untyped(noEncontrado());
    if (actual.estado !== "programado") return response.untyped(cerrado());
    if (!actual.editable) {
      return response.untyped(
        error(
          409,
          "vuelo_con_reservas",
          "El vuelo tiene reservas activas o compras y no se puede editar.",
        ),
      );
    }
    const datos = await request.json();
    const validado = validarVuelo(datos, actual.id);
    if (validado instanceof Response) return response.untyped(validado);
    const [o, d, salida] = validado;
    const editado = armarVuelo(actual.id, o.codigo, d.codigo, salida, datos.duracion_minutos, [
      datos.precio_economica,
      datos.precio_primera,
    ]);
    db.vuelos[indice] = editado;
    return response(200).json(conPromociones(editado));
  }),

  // STA-00088 tiene tiquetes vendidos → vuelo_con_tiquetes (requiere fuerza mayor, iteración 3).
  http.post("/api/v1/vuelos/{vuelo_id}/cancelar", ({ params, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const vuelo = db.vuelos.find((v) => v.id === Number(params.vuelo_id));
    if (!vuelo) return response.untyped(noEncontrado());
    if (vuelo.estado !== "programado") return response.untyped(cerrado());
    if (vuelo.tiquetes_vendidos > 0) {
      return response.untyped(
        error(
          409,
          "vuelo_con_tiquetes",
          "El vuelo tiene tiquetes vendidos: requiere cancelación por fuerza mayor.",
        ),
      );
    }
    const reservas_anuladas = vuelo.reservas_activas;
    const cap = vuelo.capacidad;
    Object.assign(vuelo, {
      estado: "cancelado",
      reservas_activas: 0,
      editable: false,
      cancelable: false,
      motivo_no_editable: "El vuelo ya se realizó o está cancelado.",
      ocupacion: {
        primera: { capacidad: cap.primera, vendidas: 0, reservadas: 0, disponibles: cap.primera },
        economica: {
          capacidad: cap.economica,
          vendidas: 0,
          reservadas: 0,
          disponibles: cap.economica,
        },
      },
    });
    for (const p of db.promociones) {
      if (p.vuelo_id === vuelo.id && (p.estado === "vigente" || p.estado === "programada")) {
        p.estado = "cancelada";
      }
    }
    return response(200).json({ vuelo: conPromociones(vuelo), reservas_anuladas });
  }),

  http.get("/api/v1/vuelos/{vuelo_id}/pasajeros", ({ params, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const vuelo = db.vuelos.find((v) => v.id === Number(params.vuelo_id));
    if (!vuelo) return response.untyped(noEncontrado());
    return response(200).json({
      vuelo: vueloBase(vuelo),
      ocupacion: vuelo.ocupacion,
      pasajeros: PASAJEROS[vuelo.id] ?? [],
    });
  }),

  // Una clase que ya tiene promoción vigente o programada → promocion_duplicada (RF-23).
  http.post("/api/v1/vuelos/{vuelo_id}/promociones", async ({ params, request, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const vuelo = db.vuelos.find((v) => v.id === Number(params.vuelo_id));
    if (!vuelo) return response.untyped(noEncontrado());
    if (vuelo.estado !== "programado" || Date.parse(vuelo.salida) <= Date.now()) {
      return response.untyped(cerrado());
    }
    const datos = await request.json();
    if (Date.parse(datos.fin) <= Date.parse(datos.inicio)) {
      return response.untyped(
        error(422, "datos_invalidos", "Revisa los campos marcados.", {
          fin: "El fin debe ser posterior al inicio.",
        }),
      );
    }
    const ocupada = db.promociones.some(
      (p) =>
        p.vuelo_id === vuelo.id &&
        (p.estado === "vigente" || p.estado === "programada") &&
        p.clases.some((c) => datos.clases.includes(c)),
    );
    if (ocupada) {
      return response.untyped(
        error(
          409,
          "promocion_duplicada",
          "Este vuelo ya tiene una promoción para esa clase. Las promociones no se acumulan.",
          {
            clases: "Ya hay una promoción vigente o programada para esta clase.",
          },
        ),
      );
    }
    const inicio = new Date(datos.inicio);
    const promocion: Schemas["Promocion"] = {
      id: nuevoId(),
      porcentaje: datos.porcentaje,
      clases: datos.clases,
      inicio: aIso(inicio),
      fin: aIso(new Date(datos.fin)),
      estado: inicio.getTime() <= Date.now() ? "vigente" : "programada",
      vuelo_id: vuelo.id,
      vuelo_codigo: vuelo.codigo,
      origen: vuelo.origen,
      destino: vuelo.destino,
      salida: vuelo.salida,
      creada_en: aIso(new Date()),
    };
    db.promociones.push(promocion);
    publicarNoticia("promocion", vuelo.id, promocion.id); // RF-25
    return response(201).json(promocion);
  }),

  http.get("/api/v1/promociones", ({ query, response }) => {
    const bloqueo = exigirRol(["admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const estado = query.get("estado");
    const items = db.promociones
      .filter((p) => !estado || p.estado === estado)
      .sort((a, b) => b.creada_en.localeCompare(a.creada_en));
    return response(200).json(paginar(items, query.get("pagina"), query.get("por_pagina")));
  }),
];
