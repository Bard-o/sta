// Carrito, reservas y compras de la API simulada (docs/api/iteracion-2.md, «Mocks para el
// frontend»). La reserva vigente y la compra pendiente se miden desde que cargan los mocks.
import type { Schemas } from "@/api/client";
import { VUELOS } from "./datos";
import { aIso, sumarMinutos } from "./tiempo";

type Clase = Schemas["TiqueteViaje"]["clase"];
type EstadoTiquete = Schemas["TiqueteViaje"]["estado"];
type Persona = Omit<Schemas["ViajeroViaje"], "id" | "tiquetes">;

export type ViajeGuardado = Schemas["Viaje"] & { usuario_id: number };
export type SeleccionGuardada = {
  id: number;
  usuario_id: number;
  tramos: { vuelo_id: number; clase: Clase; precio_al_agregar: number }[];
  viajeros: number;
  agregada_en: string;
};

export const LAURA_ID = 12;
const AHORA = new Date();
const hace = (minutos: number) => aIso(sumarMinutos(AHORA, -minutos));
const dentroDe = (minutos: number) => aIso(sumarMinutos(AHORA, minutos));

const contactoLaura = { contacto_nombre: "Laura Gómez", contacto_telefono: "310 555 0192" };

export const PERSONAS = {
  laura: {
    tipo_documento: "CC",
    numero_documento: "1088345921",
    nombres: "Laura",
    apellidos: "Gómez Ríos",
    fecha_nacimiento: "1995-03-14",
    genero: "femenino",
    telefono: "310 555 0192",
    email: "laura.gomez@correo.co",
    contacto_nombre: "Jorge Gómez",
    contacto_telefono: "311 555 0101",
  },
  marta: {
    tipo_documento: "CC",
    numero_documento: "42118907",
    nombres: "Marta",
    apellidos: "Ríos Salazar",
    fecha_nacimiento: "1968-07-22",
    genero: "femenino",
    telefono: "315 555 0142",
    email: "marta.rios@correo.co",
    ...contactoLaura,
  },
  tomas: {
    tipo_documento: "TI",
    numero_documento: "1088902114",
    nombres: "Tomás",
    apellidos: "Gómez Ríos",
    fecha_nacimiento: "2012-05-02",
    genero: "masculino",
    telefono: "310 555 0192",
    email: "laura.gomez@correo.co",
    ...contactoLaura,
  },
  jorge: {
    tipo_documento: "CC",
    numero_documento: "10203040",
    nombres: "Jorge",
    apellidos: "Gómez Arango",
    fecha_nacimiento: "1966-01-30",
    genero: "masculino",
    telefono: "311 555 0101",
    email: "jorge.gomez@correo.co",
    ...contactoLaura,
  },
  ana: {
    tipo_documento: "CC",
    numero_documento: "1088765432",
    nombres: "Ana",
    apellidos: "Gómez Ríos",
    fecha_nacimiento: "1998-09-09",
    genero: "femenino",
    telefono: "314 555 0155",
    email: "ana.gomez@correo.co",
    ...contactoLaura,
  },
  camilo: {
    tipo_documento: "CC",
    numero_documento: "1088111222",
    nombres: "Camilo",
    apellidos: "Ríos Mejía",
    fecha_nacimiento: "1990-02-11",
    genero: "masculino",
    telefono: "312 555 0133",
    email: "camilo.rios@correo.co",
    contacto_nombre: "Lucía Ríos",
    contacto_telefono: "313 555 0144",
  },
  lucia: {
    tipo_documento: "CC",
    numero_documento: "1088333444",
    nombres: "Lucía",
    apellidos: "Ríos Mejía",
    fecha_nacimiento: "1993-12-01",
    genero: "femenino",
    telefono: "313 555 0144",
    email: "lucia.rios@correo.co",
    contacto_nombre: "Camilo Ríos",
    contacto_telefono: "312 555 0133",
  },
} satisfies Record<string, Persona>;

/** El vuelo de un tramo, con los campos que trae un Viaje. */
export function vueloViaje(v: Schemas["VueloAdmin"]): Schemas["VueloViaje"] {
  return {
    id: v.id,
    codigo: v.codigo,
    tipo: v.tipo,
    origen: v.origen,
    destino: v.destino,
    salida: v.salida,
    llegada: v.llegada,
    duracion_minutos: v.duracion_minutos,
    estado: v.estado,
  };
}

type ViajeroMock = {
  id: number;
  persona: Persona;
  sillas: [numero: number, silla: string][]; // una por tramo
};

/** Arma un viaje de un solo tramo y una sola clase, con totales coherentes. */
function armarViaje(d: {
  id: number;
  tipo: ViajeGuardado["tipo"];
  codigo: string;
  estado: ViajeGuardado["estado"];
  vuelo: number;
  clase: Clase;
  precio: number;
  estadoTiquete: EstadoTiquete;
  creada_en: string;
  vence_en: string | null;
  pagada_en?: string | null;
  viajeros: ViajeroMock[];
}): ViajeGuardado {
  const vuelo = VUELOS.find((v) => v.id === d.vuelo)!;
  const viajeros = d.viajeros.map((v) => ({
    ...v.persona,
    id: v.id,
    tiquetes: v.sillas.map(([numero, silla], tramo) => ({
      id: v.id * 10 + tramo,
      tramo,
      clase: d.clase,
      silla,
      numero_silla: numero,
      precio: d.precio,
      estado: d.estadoTiquete,
    })),
  }));
  const tiquetes = viajeros.flatMap((v) => v.tiquetes);
  const pendientes = tiquetes.filter((t) => t.estado === "reservado" || t.estado === "bloqueado");
  return {
    id: d.id,
    usuario_id: LAURA_ID,
    tipo: d.tipo,
    codigo: d.codigo,
    estado: d.estado,
    reserva_id: null,
    compra_id: null,
    creada_en: d.creada_en,
    vence_en: d.vence_en,
    pagada_en: d.pagada_en ?? null,
    total: tiquetes.reduce((s, t) => s + t.precio, 0),
    total_pendiente: pendientes.reduce((s, t) => s + t.precio, 0),
    tramos: [{ vuelo: vueloViaje(vuelo) }],
    viajeros,
  };
}

const { laura, marta, tomas, jorge, ana, camilo, lucia } = PERSONAS;

export const VIAJES: ViajeGuardado[] = [
  armarViaje({
    id: 41,
    tipo: "reserva",
    codigo: "H4N8WQ",
    estado: "vigente",
    vuelo: 131,
    clase: "economica",
    precio: 262_500,
    estadoTiquete: "reservado",
    creada_en: hace(180),
    vence_en: dentroDe(21 * 60),
    viajeros: [
      { id: 4101, persona: laura, sillas: [[88, "18C"]] },
      { id: 4102, persona: marta, sillas: [[89, "18D"]] },
      { id: 4103, persona: tomas, sillas: [[90, "18E"]] },
    ],
  }),
  armarViaje({
    id: 42,
    tipo: "reserva",
    codigo: "B3M9TA",
    estado: "vencida",
    vuelo: 142,
    clase: "economica",
    precio: 185_000,
    estadoTiquete: "vencido",
    creada_en: "2026-11-01T14:02:00Z",
    vence_en: "2026-11-02T14:02:00Z",
    viajeros: [{ id: 4201, persona: laura, sillas: [[61, "13A"]] }],
  }),
  armarViaje({
    id: 43,
    tipo: "reserva",
    codigo: "R5T2LM",
    estado: "vigente",
    vuelo: 135,
    clase: "economica",
    precio: 300_000,
    estadoTiquete: "reservado",
    creada_en: hace(60),
    vence_en: dentroDe(23 * 60),
    viajeros: [
      { id: 4301, persona: camilo, sillas: [[41, "9A"]] },
      { id: 4302, persona: lucia, sillas: [[42, "9B"]] },
    ],
  }),
  armarViaje({
    id: 901,
    tipo: "compra",
    codigo: "K7Q2PX",
    estado: "pendiente",
    vuelo: 160,
    clase: "economica",
    precio: 400_000,
    estadoTiquete: "bloqueado",
    creada_en: hace(0),
    vence_en: dentroDe(15),
    viajeros: [
      { id: 9011, persona: laura, sillas: [[88, "18C"]] },
      { id: 9012, persona: marta, sillas: [[89, "18D"]] },
    ],
  }),
  armarViaje({
    id: 902,
    tipo: "compra",
    codigo: "Z9Y8X7",
    estado: "vencida",
    vuelo: 142,
    clase: "economica",
    precio: 185_000,
    estadoTiquete: "vencido",
    creada_en: "2026-11-14T15:00:00Z",
    vence_en: "2026-11-14T15:15:00Z",
    viajeros: [
      { id: 9021, persona: laura, sillas: [[63, "13C"]] },
      { id: 9022, persona: marta, sillas: [[64, "13D"]] },
    ],
  }),
  armarViaje({
    id: 903,
    tipo: "compra",
    codigo: "K7Q2MX",
    estado: "activa",
    vuelo: 88,
    clase: "economica",
    precio: 2_450_000,
    estadoTiquete: "comprado",
    creada_en: "2026-10-02T14:50:00Z",
    vence_en: null,
    pagada_en: "2026-10-02T15:00:00Z",
    viajeros: [
      { id: 9031, persona: laura, sillas: [[112, "17B"]] },
      { id: 9032, persona: jorge, sillas: [[113, "17C"]] },
    ],
  }),
  armarViaje({
    id: 904,
    tipo: "compra",
    codigo: "P3X7KD",
    estado: "activa",
    vuelo: 135,
    clase: "economica",
    precio: 300_000,
    estadoTiquete: "comprado",
    creada_en: "2026-11-03T16:10:00Z",
    vence_en: null,
    pagada_en: "2026-11-03T16:20:00Z",
    viajeros: [
      { id: 9041, persona: laura, sillas: [[56, "12A"]] },
      { id: 9042, persona: jorge, sillas: [[57, "12B"]] },
      { id: 9043, persona: ana, sillas: [[58, "12C"]] },
    ],
  }),
];

export const SELECCIONES: SeleccionGuardada[] = [
  {
    id: 71,
    usuario_id: LAURA_ID,
    viajeros: 2,
    agregada_en: "2026-11-05T14:00:00Z",
    tramos: [{ vuelo_id: 131, clase: "economica", precio_al_agregar: 262_500 }],
  },
  {
    id: 72,
    usuario_id: LAURA_ID,
    viajeros: 2,
    agregada_en: "2026-11-06T10:00:00Z",
    tramos: [{ vuelo_id: 157, clase: "economica", precio_al_agregar: 320_000 }],
  },
  {
    id: 73,
    usuario_id: LAURA_ID,
    viajeros: 2,
    agregada_en: "2026-11-10T09:30:00Z",
    tramos: [
      { vuelo_id: 101, clase: "primera", precio_al_agregar: 4_100_000 },
      { vuelo_id: 132, clase: "economica", precio_al_agregar: 1_750_000 },
    ],
  },
];
