// Módulo reservas (HU-24 a HU-27): reservas, compras en dos pasos y Mis viajes. Solo cliente;
// reservar, comprar, confirmar y pagar exigen el correo verificado (pedrorios no lo tiene).
// Valores que disparan cada error: docs/api/iteracion-2.md, «Mocks para el frontend».
import type { Schemas } from "@/api/client";
import { cop } from "@/lib/format";
import { type ViajeGuardado, vueloViaje } from "../datos-viajes";
import {
  aViaje,
  db,
  documentoActivo,
  error,
  exigirRol,
  nuevoId,
  ocupar,
  paginar,
  precioVigente,
  procesarVencimientos,
  registrarMovimiento,
  reservasActivas,
  saldoDe,
  sesion,
  soltar,
  tiquetesActivos,
  vuelosDeTramos,
} from "../estado";
import { http } from "../http";
import {
  BLOQUEO_COMPRA_MIN,
  type Clase,
  edadEn,
  fechaLocal,
  hoyEnColombia,
  MAX_TIQUETES,
  nombreDeSilla,
  nuevoCodigo,
  primeraSilla,
  venceEn,
  VIGENCIA_RESERVA_MIN,
  ZONA_COLOMBIA,
} from "../reglas";
import { aIso } from "../tiempo";

type VueloAdmin = Schemas["VueloAdmin"];
type ViajeEntrada = Schemas["ViajeEntrada"];
type Viajero = Schemas["ViajeroViaje"];
const CLASES: Clase[] = ["economica", "primera"];

const usuarioId = () => sesion.get()!.id;
const invalido = (campos: Record<string, string>) =>
  error(422, "datos_invalidos", "Revisa los campos marcados.", campos);
const MENSAJE_DOCUMENTO = "Uno de los documentos ya tiene un tiquete activo en este vuelo.";
const sinSaldo = (falta: number) =>
  error(409, "saldo_insuficiente", `Tu saldo no alcanza: te faltan ${cop(falta)}.`);

function exigirClienteVerificado(): Response | undefined {
  const bloqueo = exigirRol(["cliente"]);
  if (bloqueo) return bloqueo;
  if (!sesion.get()?.email_verificado) {
    return error(403, "correo_no_verificado", "Verifica tu correo para reservar o comprar.");
  }
  return undefined;
}

function delCliente(id: number, tipo: ViajeGuardado["tipo"]) {
  procesarVencimientos();
  return db.viajes.find((v) => v.id === id && v.tipo === tipo && v.usuario_id === usuarioId());
}

/** HU-24: las reglas comunes de reservar y comprar, en el orden del contrato. */
function validarViaje(datos: ViajeEntrada): VueloAdmin[] | Response {
  const vuelos = vuelosDeTramos(datos.tramos.map((t) => t.vuelo_id));
  if (vuelos instanceof Response) return vuelos;
  const hoy = hoyEnColombia();
  for (const [i, v] of datos.viajeros.entries()) {
    if (v.clases.length !== vuelos.length) {
      return invalido({ [`viajeros.${i}.clases`]: "Debe traer una clase por cada tramo." });
    }
    if (v.fecha_nacimiento > hoy) {
      return invalido({
        [`viajeros.${i}.fecha_nacimiento`]: "La fecha de nacimiento no puede ser futura.",
      });
    }
  }
  const vistos = new Set<string>();
  for (const [i, v] of datos.viajeros.entries()) {
    const llave = `${v.tipo_documento}-${v.numero_documento.toUpperCase()}`;
    const campo = `viajeros.${i}.numero_documento`;
    if (vistos.has(llave)) {
      return error(409, "viajero_duplicado", MENSAJE_DOCUMENTO, {
        [campo]: "Este documento ya tiene un tiquete activo en este vuelo.",
      });
    }
    vistos.add(llave);
    if (vuelos.some((vuelo) => documentoActivo(v.tipo_documento, v.numero_documento, vuelo.id))) {
      return error(409, "viajero_duplicado", MENSAJE_DOCUMENTO, {
        [campo]: "Este documento ya tiene un tiquete activo en este vuelo.",
      });
    }
  }
  for (const vuelo of vuelos) {
    const dia = fechaLocal(vuelo.salida, vuelo.origen.zona_horaria);
    const edades = datos.viajeros.map((v) => edadEn(v.fecha_nacimiento, dia));
    if (edades.every((edad) => edad < 18)) {
      return error(
        422,
        "menor_sin_adulto",
        "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.",
        Object.fromEntries(
          edades.map((_, i) => [
            `viajeros.${i}.fecha_nacimiento`,
            "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.",
          ]),
        ),
      );
    }
  }
  for (const vuelo of vuelos) {
    const activos = tiquetesActivos(usuarioId(), vuelo.id);
    if (activos + datos.viajeros.length > MAX_TIQUETES) {
      return error(
        409,
        "limite_tiquetes",
        `Un cliente puede tener máximo ${MAX_TIQUETES} tiquetes activos en el mismo vuelo.`,
      );
    }
  }
  for (const [j, vuelo] of vuelos.entries()) {
    for (const clase of CLASES) {
      const pedidas = datos.viajeros.filter((v) => v.clases[j] === clase).length;
      const quedan = vuelo.ocupacion[clase].disponibles;
      if (pedidas > quedan) {
        return error(409, "clase_agotada", "No quedan sillas suficientes en esta clase.");
      }
    }
  }
  return vuelos;
}

/** Crea la reserva (vigente) o la compra (pendiente): sillas consecutivas por vuelo y clase. */
function crearViaje(tipo: ViajeGuardado["tipo"], datos: ViajeEntrada, vuelos: VueloAdmin[]) {
  const ahora = Date.now();
  const estado = tipo === "reserva" ? "reservado" : "bloqueado";
  const proxima = new Map<string, number>();
  const viajeros: Viajero[] = datos.viajeros.map(({ clases, ...persona }) => ({
    ...persona,
    id: nuevoId(),
    tiquetes: vuelos.map((vuelo, tramo) => {
      const clase = clases[tramo];
      const llave = `${vuelo.id}-${clase}`;
      const { vendidas, reservadas } = vuelo.ocupacion[clase];
      const numero = proxima.get(llave) ?? primeraSilla(vuelo.tipo, clase) + vendidas + reservadas;
      proxima.set(llave, numero + 1);
      return {
        id: nuevoId(),
        tramo,
        clase,
        silla: nombreDeSilla(vuelo.tipo, clase, numero),
        numero_silla: numero,
        precio: precioVigente(vuelo, clase),
        estado,
      };
    }),
  }));
  for (const viajero of viajeros) {
    for (const t of viajero.tiquetes) ocupar(vuelos[t.tramo].id, t.clase, 1, "reservadas");
  }
  const total = viajeros.flatMap((v) => v.tiquetes).reduce((s, t) => s + t.precio, 0);
  const viaje: ViajeGuardado = {
    id: nuevoId(),
    usuario_id: usuarioId(),
    tipo,
    codigo: nuevoCodigo(),
    estado: tipo === "reserva" ? "vigente" : "pendiente",
    reserva_id: null,
    compra_id: null,
    creada_en: aIso(new Date(ahora)),
    vence_en: venceEn(
      vuelos,
      tipo === "reserva" ? VIGENCIA_RESERVA_MIN : BLOQUEO_COMPRA_MIN,
      ahora,
    ),
    pagada_en: null,
    total,
    total_pendiente: total,
    tramos: vuelos.map((v) => ({ vuelo: vueloViaje(v) })),
    viajeros,
  };
  reservasActivas(viaje, 1);
  db.viajes.push(viaje);
  return viaje;
}

/** Pasa los tiquetes `de` a comprados y mueve sus sillas de reservadas a vendidas. */
function vender(viaje: ViajeGuardado, viajeros: Viajero[], de: "reservado" | "bloqueado") {
  for (const viajero of viajeros) {
    for (const t of viajero.tiquetes) {
      if (t.estado !== de) continue;
      t.estado = "comprado";
      const vueloId = viaje.tramos[t.tramo].vuelo.id;
      ocupar(vueloId, t.clase, -1, "reservadas");
      ocupar(vueloId, t.clase, 1, "vendidas");
    }
  }
}

export const reservasHandlers = [
  http.post("/api/v1/reservas", async ({ request, response }) => {
    const bloqueo = exigirClienteVerificado();
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const vuelos = validarViaje(datos);
    if (vuelos instanceof Response) return response.untyped(vuelos);
    return response(201).json(aViaje(crearViaje("reserva", datos, vuelos)));
  }),

  http.post("/api/v1/compras", async ({ request, response }) => {
    const bloqueo = exigirClienteVerificado();
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const vuelos = validarViaje(datos);
    if (vuelos instanceof Response) return response.untyped(vuelos);
    return response(201).json(aViaje(crearViaje("compra", datos, vuelos)));
  }),

  http.get("/api/v1/compras/{compra_id}", ({ params, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const compra = delCliente(Number(params.compra_id), "compra");
    if (!compra) return response.untyped(error(404, "no_encontrado", "La compra no existe."));
    return response(200).json(aViaje(compra));
  }),

  // 901 (K7Q2PX) se puede confirmar; 902 (Z9Y8X7) tiene el bloqueo vencido.
  http.post("/api/v1/compras/{compra_id}/confirmar", ({ params, response }) => {
    const bloqueo = exigirClienteVerificado();
    if (bloqueo) return response.untyped(bloqueo);
    const compra = delCliente(Number(params.compra_id), "compra");
    if (!compra) return response.untyped(error(404, "no_encontrado", "La compra no existe."));
    if (compra.estado === "activa") {
      return response.untyped(error(409, "estado_invalido", "La compra ya está pagada."));
    }
    if (compra.estado !== "pendiente") {
      return response.untyped(
        error(
          409,
          "bloqueo_vencido",
          "Las sillas se liberaron porque pasaron 15 minutos sin confirmar. Vuelve a empezar la compra.",
        ),
      );
    }
    const saldo = saldoDe(usuarioId());
    if (saldo < compra.total_pendiente)
      return response.untyped(sinSaldo(compra.total_pendiente - saldo));
    registrarMovimiento(usuarioId(), "compra", -compra.total_pendiente, compra.codigo);
    vender(compra, compra.viajeros, "bloqueado");
    reservasActivas(compra, -1);
    Object.assign(compra, {
      estado: "activa",
      vence_en: null,
      pagada_en: aIso(new Date()),
      total_pendiente: 0,
    });
    return response(200).json(aViaje(compra));
  }),

  http.delete("/api/v1/compras/{compra_id}", ({ params, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const compra = delCliente(Number(params.compra_id), "compra");
    if (!compra) return response.untyped(error(404, "no_encontrado", "La compra no existe."));
    if (compra.estado === "activa") {
      return response.untyped(error(409, "estado_invalido", "La compra ya está pagada."));
    }
    if (compra.estado === "pendiente") soltar(compra, "bloqueado", "cancelado", "cancelada");
    return response(204).empty();
  }),

  // H4N8WQ (41): pagar solo a Tomás (4103) → menor_sin_adulto. B3M9TA (42) está vencida.
  http.post("/api/v1/reservas/{reserva_id}/pagar", async ({ params, request, response }) => {
    const bloqueo = exigirClienteVerificado();
    if (bloqueo) return response.untyped(bloqueo);
    const reserva = delCliente(Number(params.reserva_id), "reserva");
    if (!reserva) return response.untyped(error(404, "no_encontrado", "La reserva no existe."));
    if (reserva.estado !== "vigente") {
      return response.untyped(
        error(
          409,
          "reserva_no_vigente",
          "La reserva ya no está vigente: venció, se canceló o ya está pagada.",
        ),
      );
    }
    const datos = await request.json();
    const pendientes = reserva.viajeros.filter((v) =>
      v.tiquetes.some((t) => t.estado === "reservado"),
    );
    const ids = datos.viajero_ids ?? pendientes.map((v) => v.id);
    const elegidos = pendientes.filter((v) => ids.includes(v.id));
    if (elegidos.length === 0 || elegidos.length !== ids.length) {
      return response.untyped(
        invalido({ viajero_ids: "Elige viajeros de esta reserva que sigan sin pagar." }),
      );
    }
    const pagados = reserva.viajeros.filter((v) => v.tiquetes.some((t) => t.estado === "comprado"));
    for (const { vuelo } of reserva.tramos) {
      const dia = fechaLocal(vuelo.salida, vuelo.origen.zona_horaria);
      if (![...pagados, ...elegidos].some((v) => edadEn(v.fecha_nacimiento, dia) >= 18)) {
        return response.untyped(
          error(
            422,
            "menor_sin_adulto",
            "Un menor de edad debe viajar con al menos un adulto en el mismo vuelo.",
            {
              viajero_ids: "Paga también a un adulto: un menor no puede quedar solo en la compra.",
            },
          ),
        );
      }
    }
    const total = elegidos
      .flatMap((v) => v.tiquetes)
      .filter((t) => t.estado === "reservado")
      .reduce((s, t) => s + t.precio, 0);
    const saldo = saldoDe(usuarioId());
    if (saldo < total) return response.untyped(sinSaldo(total - saldo));
    registrarMovimiento(usuarioId(), "compra", -total, reserva.codigo);
    vender(reserva, elegidos, "reservado");
    const ahora = aIso(new Date());
    const copias = structuredClone(elegidos);
    let compra = db.viajes.find((v) => v.tipo === "compra" && v.reserva_id === reserva.id);
    if (compra) {
      compra.viajeros.push(...copias);
      compra.total += total;
      compra.pagada_en = ahora;
    } else {
      compra = {
        id: nuevoId(),
        usuario_id: usuarioId(),
        tipo: "compra",
        codigo: reserva.codigo,
        estado: "activa",
        reserva_id: reserva.id,
        compra_id: null,
        creada_en: ahora,
        vence_en: null,
        pagada_en: ahora,
        total,
        total_pendiente: 0,
        tramos: structuredClone(reserva.tramos),
        viajeros: copias,
      };
      db.viajes.push(compra);
      reserva.compra_id = compra.id;
    }
    reserva.total_pendiente -= total;
    if (reserva.total_pendiente === 0) {
      reserva.estado = "pagada";
      reservasActivas(reserva, -1);
    }
    return response(200).json({ reserva: aViaje(reserva), compra: aViaje(compra) });
  }),

  http.get("/api/v1/mis-viajes", ({ request, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    procesarVencimientos();
    const q = new URL(request.url).searchParams;
    const tipo = q.get("tipo");
    if (tipo !== "reserva" && tipo !== "compra") {
      return response.untyped(invalido({ tipo: "No es una opción válida." }));
    }
    const [estado, desde, hasta] = [q.get("estado"), q.get("desde"), q.get("hasta")];
    if (desde && hasta && hasta < desde) {
      return response.untyped(
        error(422, "rango_invalido", "Revisa los rangos marcados.", {
          hasta: "La fecha final no puede ser anterior a la inicial.",
        }),
      );
    }
    const items = db.viajes
      .filter((v) => v.usuario_id === usuarioId() && v.tipo === tipo)
      .filter((v) => tipo === "reserva" || v.pagada_en !== null) // las compras sin pagar no se listan
      .filter((v) => !estado || v.estado === estado)
      .filter((v) => {
        const dia = fechaLocal(v.tramos[0].vuelo.salida, ZONA_COLOMBIA);
        return (!desde || dia >= desde) && (!hasta || dia <= hasta);
      })
      .sort((a, b) => b.creada_en.localeCompare(a.creada_en))
      .map(aViaje);
    return response(200).json(paginar(items, q.get("pagina"), q.get("por_pagina")));
  }),
];
