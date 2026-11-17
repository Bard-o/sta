// Estado en memoria de la API simulada: lo que se crea o cambia dura hasta recargar la página
// (la sesión sí sobrevive a la recarga, en sessionStorage).
import { HttpResponse } from "msw";
import type { Schemas } from "@/api/client";
import {
  ADMINISTRADORES,
  CUENTAS,
  ciudad,
  precioConDescuento,
  PROMOCIONES,
  TOKEN_INVITACION_MOCK,
  VUELOS,
} from "./datos";
import { MOVIMIENTOS, TARJETAS, type MovimientoGuardado } from "./datos-monedero";
import { SELECCIONES, VIAJES, type ViajeGuardado } from "./datos-viajes";
import { aLaVenta } from "./reglas";
import { aIso } from "./tiempo";

type Usuario = Schemas["UsuarioSalida"];
type Rol = Usuario["rol"];
type Noticia = Schemas["Noticia"];
type VueloAdmin = Schemas["VueloAdmin"];

export type InvitacionMock = {
  token: string;
  admin_id: number;
  email: string;
  expira_en: string;
  usado: boolean;
};

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
  invitaciones: [
    {
      token: TOKEN_INVITACION_MOCK,
      admin_id: 5,
      email: "jorge.torres@avianco.test",
      expira_en: "2099-12-31T23:59:00Z",
      usado: false,
    },
  ] as InvitacionMock[],
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
  selecciones: structuredClone(SELECCIONES),
  viajes: structuredClone(VIAJES),
  tarjetas: structuredClone(TARJETAS),
  movimientos: structuredClone(MOVIMIENTOS),
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

/** Igual que require_role del backend: 401 sin sesión y 403 con otro rol. */
export function exigirRol(roles: Rol[]) {
  const usuario = sesion.get();
  if (!usuario) return error(401, "no_autenticado", "Inicia sesión para continuar.");
  if (!roles.includes(usuario.rol)) {
    return error(403, "sin_permiso", "Tu rol no tiene permiso para esta acción.");
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

// ---------- Iteración 2: ocupación, vencimientos y saldo ----------

type ClaseVuelo = "economica" | "primera";
type EstadoTiquete = Schemas["TiqueteViaje"]["estado"];

/** Precio vigente de una clase, con la promoción vigente si la hay (RF-24). */
export function precioVigente(v: VueloAdmin, clase: ClaseVuelo): number {
  return vueloDetalle(conPromociones(v))[clase].precio_vigente;
}

/** Suma `n` sillas (o las quita, con n < 0) a la ocupación del vuelo. */
export function ocupar(
  vueloId: number,
  clase: ClaseVuelo,
  n: number,
  columna: "reservadas" | "vendidas",
) {
  const v = db.vuelos.find((x) => x.id === vueloId);
  if (!v) return;
  const c = v.ocupacion[clase];
  c[columna] += n;
  c.disponibles = c.capacidad - c.vendidas - c.reservadas;
  v.tiquetes_vendidos = v.ocupacion.primera.vendidas + v.ocupacion.economica.vendidas;
}

/** Reservas vigentes y compras pendientes del vuelo (impiden editarlo, HU-15). */
export function reservasActivas(viaje: ViajeGuardado, n: number) {
  for (const { vuelo } of viaje.tramos) {
    const v = db.vuelos.find((x) => x.id === vuelo.id);
    if (v) v.reservas_activas = Math.max(0, v.reservas_activas + n);
  }
}

/** Un tiquete cuenta como activo en una reserva si sigue reservado, y en una compra si está
 *  comprado o bloqueado: un viajero pagado no cuenta dos veces (RF-32, RF-34). */
function activo(viaje: ViajeGuardado, estado: EstadoTiquete): boolean {
  return viaje.tipo === "reserva"
    ? estado === "reservado"
    : estado === "comprado" || estado === "bloqueado";
}

function tiquetesActivosDe(viajes: ViajeGuardado[], vueloId: number) {
  return viajes.flatMap((viaje) =>
    viaje.viajeros.flatMap((viajero) =>
      viajero.tiquetes
        .filter((t) => activo(viaje, t.estado) && viaje.tramos[t.tramo].vuelo.id === vueloId)
        .map((t) => ({ viajero, t })),
    ),
  );
}

/** RF-32: tiquetes activos del cliente en el vuelo (reservados, comprados y bloqueados). */
export function tiquetesActivos(usuarioId: number, vueloId: number): number {
  procesarVencimientos();
  return tiquetesActivosDe(
    db.viajes.filter((v) => v.usuario_id === usuarioId),
    vueloId,
  ).length;
}

/** RF-34: el documento ya tiene un tiquete activo en el vuelo, de cualquier cliente. */
export function documentoActivo(tipo: string, numero: string, vueloId: number): boolean {
  procesarVencimientos();
  return tiquetesActivosDe(db.viajes, vueloId).some(
    ({ viajero }) =>
      viajero.tipo_documento === tipo &&
      viajero.numero_documento.toUpperCase() === numero.toUpperCase(),
  );
}

/** Libera las sillas de una reserva o compra que termina sin pagarse (RF-37, SUP-15): vence
 *  (`vencido`, `vencida`) o la suelta el cliente o el vuelo (`cancelado`, `cancelada`). */
export function soltar(
  viaje: ViajeGuardado,
  de: EstadoTiquete,
  a: EstadoTiquete,
  estado: ViajeGuardado["estado"],
) {
  for (const viajero of viaje.viajeros) {
    for (const t of viajero.tiquetes) {
      if (t.estado !== de) continue;
      t.estado = a;
      ocupar(viaje.tramos[t.tramo].vuelo.id, t.clase, -1, "reservadas");
    }
  }
  reservasActivas(viaje, -1);
  viaje.estado = estado;
  viaje.total_pendiente = 0;
}

/** Lo que hacen las tareas `reservas.vencer_reservas` y `reservas.liberar_bloqueos`. */
export function procesarVencimientos(ahora = Date.now()) {
  for (const v of db.viajes) {
    if (!v.vence_en || Date.parse(v.vence_en) > ahora) continue;
    if (v.tipo === "reserva" && v.estado === "vigente")
      soltar(v, "reservado", "vencido", "vencida");
    if (v.tipo === "compra" && v.estado === "pendiente") {
      soltar(v, "bloqueado", "vencido", "vencida");
    }
  }
}

/** Valida los vuelos de los tramos como el backend: existen, se venden y el regreso cuadra. */
export function vuelosDeTramos(vueloIds: number[]): VueloAdmin[] | Response {
  const vuelos: VueloAdmin[] = [];
  for (const [i, id] of vueloIds.entries()) {
    const campo = `tramos.${i}.vuelo_id`;
    const v = db.vuelos.find((x) => x.id === id);
    if (!v || v.estado !== "programado") {
      return error(409, "vuelo_no_disponible", "Uno de los vuelos ya no está a la venta.", {
        [campo]: "El vuelo no existe o ya no está programado.",
      });
    }
    if (!aLaVenta(v)) {
      return error(
        409,
        "fuera_de_plazo",
        `La venta de ${v.codigo} ya cerró: cierra 1 hora antes de la salida (3 horas si es internacional).`,
        { [campo]: "Ya no se puede reservar ni comprar." },
      );
    }
    vuelos.push(v);
  }
  if (vuelos.length === 2) {
    const [ida, regreso] = vuelos;
    const invalido =
      regreso.id === ida.id ||
      regreso.origen.codigo !== ida.destino.codigo ||
      Date.parse(regreso.salida) <= Date.parse(ida.llegada);
    if (invalido) {
      return error(
        422,
        "regreso_invalido",
        `El regreso debe salir de ${ida.destino.nombre} después de la llegada de la ida.`,
        { "tramos.1.vuelo_id": "Elige un regreso que salga después de tu llegada." },
      );
    }
  }
  return vuelos;
}

export function saldoDe(usuarioId: number): number {
  return db.movimientos.filter((m) => m.usuario_id === usuarioId).reduce((s, m) => s + m.valor, 0);
}

export function registrarMovimiento(
  usuarioId: number,
  tipo: MovimientoGuardado["tipo"],
  valor: number,
  referencia: string,
): MovimientoGuardado {
  const movimiento: MovimientoGuardado = {
    id: nuevoId(),
    usuario_id: usuarioId,
    tipo,
    valor,
    saldo_resultante: saldoDe(usuarioId) + valor,
    referencia,
    creado_en: aIso(new Date()),
  };
  db.movimientos.push(movimiento);
  return movimiento;
}

/** Quita el dueño antes de responder: la API no lo expone. */
export function aViaje({ usuario_id, ...viaje }: ViajeGuardado): Schemas["Viaje"] {
  void usuario_id;
  return viaje;
}

export function aMovimiento({ usuario_id, ...m }: MovimientoGuardado): Schemas["Movimiento"] {
  void usuario_id;
  return m;
}
