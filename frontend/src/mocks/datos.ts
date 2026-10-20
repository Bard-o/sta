// Datos de ejemplo de la API simulada (docs/api/iteracion-1.md). Todos tipados con los schemas
// generados: si el contrato cambia, `npm run typecheck` señala qué ajustar aquí.
//
// Usuarios de prueba (contraseña de todos: CONTRASENA_MOCK):
//   lauragomez  cliente con el correo verificado y una compra activa (no puede desactivarse)
//   pedrorios   cliente con el correo sin verificar
//   cruiz       administrador          jtorres   administrador con el registro incompleto
//   root        root                   amejia    administrador inactivo («cuenta inactiva»)
//   bloqueado   cualquier contraseña responde 429 (HU-03, 5 intentos fallidos)
import type { Schemas } from "@/api/client";
import { aIso, sumarMinutos } from "./tiempo";

type Ciudad = Schemas["Ciudad"];
type CiudadResumen = Schemas["CiudadResumen"];
type VueloAdmin = Schemas["VueloAdmin"];
type Promocion = Schemas["Promocion"];
type Clase = Promocion["clases"][number];

export const CONTRASENA_MOCK = "Clave1234";

// ---------- Ciudades (subconjunto del catálogo de RF-12) ----------

const nacional = (codigo: string, nombre: string, internacional = false): Ciudad => ({
  codigo,
  nombre,
  pais: "Colombia",
  zona_horaria: "America/Bogota",
  tipo: "nacional",
  habilitada_internacional: internacional,
  imagen_url: `/imagenes/ciudades/${codigo}.jpg`,
});

const exterior = (codigo: string, nombre: string, pais: string, zona: string): Ciudad => ({
  codigo,
  nombre,
  pais,
  zona_horaria: zona,
  tipo: "internacional",
  habilitada_internacional: false,
  imagen_url: `/imagenes/ciudades/${codigo}.jpg`,
});

export const CIUDADES: Ciudad[] = [
  nacional("BOG", "Bogotá", true),
  nacional("MDE", "Medellín", true),
  nacional("CLO", "Cali", true),
  nacional("CTG", "Cartagena", true),
  nacional("PEI", "Pereira", true),
  nacional("BAQ", "Barranquilla"),
  nacional("BGA", "Bucaramanga"),
  nacional("MZL", "Manizales"),
  nacional("SMR", "Santa Marta"),
  nacional("LET", "Leticia"),
  exterior("MAD", "Madrid", "España", "Europe/Madrid"),
  exterior("LHR", "Londres", "Reino Unido", "Europe/London"),
  exterior("JFK", "Nueva York", "Estados Unidos", "America/New_York"),
  exterior("EZE", "Buenos Aires", "Argentina", "America/Argentina/Buenos_Aires"),
  exterior("MIA", "Miami", "Estados Unidos", "America/New_York"),
];

export function ciudad(codigo: string): Ciudad | undefined {
  return CIUDADES.find((c) => c.codigo === codigo);
}

export function resumenCiudad(c: Ciudad): CiudadResumen {
  return { codigo: c.codigo, nombre: c.nombre, zona_horaria: c.zona_horaria };
}

// ---------- Vuelos ----------

export function capacidad(tipo: VueloAdmin["tipo"]): VueloAdmin["capacidad"] {
  return tipo === "nacional"
    ? { primera: 25, economica: 125, total: 150 }
    : { primera: 50, economica: 200, total: 250 };
}

export function tipoDeRuta(origen: Ciudad, destino: Ciudad): VueloAdmin["tipo"] {
  return origen.tipo === "internacional" || destino.tipo === "internacional"
    ? "internacional"
    : "nacional";
}

type Ventas = {
  vendidas?: [primera: number, economica: number];
  reservadas?: [primera: number, economica: number];
  reservas_activas?: number;
};

/** Arma un VueloAdmin coherente: tipo, capacidad, llegada, ocupación y bloqueos. */
export function armarVuelo(
  id: number,
  origen: string,
  destino: string,
  salida: string,
  duracion_minutos: number,
  precios: [economica: number, primera: number],
  estado: VueloAdmin["estado"] = "programado",
  ventas: Ventas = {},
): VueloAdmin {
  const o = ciudad(origen)!;
  const d = ciudad(destino)!;
  const tipo = tipoDeRuta(o, d);
  const cap = capacidad(tipo);
  const [vp, ve] = ventas.vendidas ?? [0, 0];
  const [rp, re] = ventas.reservadas ?? [0, 0];
  const reservas_activas = ventas.reservas_activas ?? 0;
  const tiquetes_vendidos = vp + ve;
  const programado = estado === "programado";
  const conVentas = tiquetes_vendidos > 0 || reservas_activas > 0;
  return {
    id,
    codigo: `STA-${String(id).padStart(5, "0")}`,
    tipo,
    origen: resumenCiudad(o),
    destino: resumenCiudad(d),
    salida,
    llegada: aIso(sumarMinutos(new Date(salida), duracion_minutos)),
    duracion_minutos,
    precio_economica: precios[0],
    precio_primera: precios[1],
    capacidad: cap,
    estado,
    ocupacion: {
      primera: {
        capacidad: cap.primera,
        vendidas: vp,
        reservadas: rp,
        disponibles: cap.primera - vp - rp,
      },
      economica: {
        capacidad: cap.economica,
        vendidas: ve,
        reservadas: re,
        disponibles: cap.economica - ve - re,
      },
    },
    reservas_activas,
    tiquetes_vendidos,
    editable: programado && !conVentas,
    motivo_no_editable: !programado
      ? "El vuelo ya se realizó o está cancelado."
      : conVentas
        ? "El vuelo tiene reservas activas o compras."
        : null,
    cancelable: programado && tiquetes_vendidos === 0,
    promociones: [],
  };
}

export const VUELOS: VueloAdmin[] = [
  // Programados (wireframes S08, S09, S11, S13)
  armarVuelo(31, "PEI", "BOG", "2026-12-10T11:00:00Z", 50, [280_000, 750_000]),
  armarVuelo(51, "PEI", "MDE", "2026-12-10T12:40:00Z", 45, [240_000, 690_000], "programado", {
    reservadas: [0, 3],
    reservas_activas: 2,
  }),
  armarVuelo(76, "BOG", "MIA", "2026-10-29T04:30:00Z", 225, [1_980_000, 4_500_000], "programado", {
    vendidas: [12, 64],
  }),
  armarVuelo(88, "BOG", "MAD", "2026-12-11T03:00:00Z", 600, [2_450_000, 6_900_000], "programado", {
    vendidas: [41, 58],
    reservadas: [2, 4],
    reservas_activas: 3,
  }),
  armarVuelo(90, "MDE", "EZE", "2026-11-02T12:00:00Z", 390, [2_100_000, 5_800_000]),
  armarVuelo(92, "PEI", "CTG", "2026-11-20T14:15:00Z", 75, [320_000, 890_000]),
  // Realizados (wireframe S12)
  armarVuelo(12, "PEI", "BOG", "2026-09-29T13:05:00Z", 50, [260_000, 720_000], "realizado", {
    vendidas: [25, 113],
  }),
  armarVuelo(9, "BOG", "MAD", "2026-09-28T03:00:00Z", 600, [2_390_000, 6_700_000], "realizado", {
    vendidas: [48, 183],
  }),
  armarVuelo(7, "CLO", "CTG", "2026-09-27T22:50:00Z", 80, [310_000, 860_000], "realizado", {
    vendidas: [9, 88],
  }),
  // Cancelado
  armarVuelo(44, "BAQ", "BGA", "2026-11-05T15:30:00Z", 70, [290_000, 780_000], "cancelado"),
];

// ---------- Promociones ----------

function armarPromocion(
  id: number,
  vueloId: number,
  porcentaje: number,
  clases: Clase[],
  inicio: string,
  fin: string,
  estado: Promocion["estado"],
  creada_en: string,
): Promocion {
  const v = VUELOS.find((x) => x.id === vueloId)!;
  return {
    id,
    porcentaje,
    clases,
    inicio,
    fin,
    estado,
    vuelo_id: v.id,
    vuelo_codigo: v.codigo,
    origen: v.origen,
    destino: v.destino,
    salida: v.salida,
    creada_en,
  };
}

export const PROMOCIONES: Promocion[] = [
  armarPromocion(
    3,
    31,
    40,
    ["economica"],
    "2026-10-01T13:00:00Z",
    "2026-10-05T04:59:00Z",
    "vencida",
    "2026-09-30T20:10:00Z",
  ),
  armarPromocion(
    1,
    76,
    30,
    ["economica"],
    "2026-10-18T13:00:00Z",
    "2026-10-27T04:59:00Z",
    "vigente",
    "2026-10-18T14:12:00Z",
  ),
  armarPromocion(
    2,
    88,
    20,
    ["primera"],
    "2026-11-01T13:00:00Z",
    "2026-11-15T04:59:00Z",
    "programada",
    "2026-10-19T16:40:00Z",
  ),
];

/** Precio con descuento: entero, redondeado hacia abajo (docs/api/iteracion-1.md, HU-17). */
export function precioConDescuento(precio: number, porcentaje: number): number {
  return Math.floor((precio * (100 - porcentaje)) / 100);
}

// ---------- Pasajeros (HU-18) ----------

export const PASAJEROS: Record<number, Schemas["PasajeroVuelo"][]> = {
  12: [
    { nombres: "Ana", apellidos: "Pérez", clase: "economica", silla: "12C", numero_silla: 58 },
    { nombres: "Luis", apellidos: "Mora", clase: "primera", silla: "2A", numero_silla: 6 },
    { nombres: "Sofía", apellidos: "Rendón", clase: "economica", silla: "18D", numero_silla: 89 },
  ],
  9: [
    { nombres: "Julián", apellidos: "Ocampo", clase: "primera", silla: "3C", numero_silla: 13 },
    { nombres: "Marta", apellidos: "Salazar", clase: "economica", silla: "14E", numero_silla: 85 },
  ],
};

// ---------- Usuarios ----------

type Usuario = Schemas["UsuarioSalida"];
type Perfil = Schemas["PerfilSalida"];

export type CuentaMock = {
  usuario: Usuario;
  perfil?: Perfil;
  activo: boolean;
};

const laura: Perfil = {
  id: 12,
  nombre_usuario: "lauragomez",
  rol: "cliente",
  tipo_documento: "CC",
  numero_documento: "1088345921",
  nombres: "Laura",
  apellidos: "Gómez Ríos",
  fecha_nacimiento: "1995-03-14",
  lugar_nacimiento: "Pereira, Risaralda",
  direccion_facturacion: "Cra. 7 # 19-28, Pereira",
  genero: "femenino",
  email: "laura.gomez@correo.co",
  email_verificado: true,
  email_pendiente: null,
  telefono: "310 555 0192",
  imagen_url: null,
  suscrito_noticias: true,
};

const pedro: Perfil = {
  ...laura,
  id: 13,
  nombre_usuario: "pedrorios",
  numero_documento: "1004567890",
  nombres: "Pedro",
  apellidos: "Ríos Arango",
  fecha_nacimiento: "2001-08-02",
  genero: "masculino",
  email: "pedro.rios@correo.co",
  email_verificado: false,
  telefono: null,
  suscrito_noticias: false,
};

const carlos: Perfil = {
  id: 3,
  nombre_usuario: "cruiz",
  rol: "admin",
  tipo_documento: "CC",
  numero_documento: "10234567",
  nombres: "Carlos",
  apellidos: "Ruiz",
  fecha_nacimiento: "1988-11-21",
  lugar_nacimiento: "Manizales, Caldas",
  direccion_facturacion: "Cl. 19 # 8-34, Pereira",
  genero: "masculino",
  email: "carlos.ruiz@avianco.test",
  email_verificado: true,
  email_pendiente: null,
  telefono: "315 222 0101",
  imagen_url: null,
  suscrito_noticias: false,
};

export function usuarioDe(perfil: Perfil): Usuario {
  return {
    id: perfil.id,
    nombre_usuario: perfil.nombre_usuario,
    email: perfil.email,
    rol: perfil.rol,
    email_verificado: perfil.email_verificado,
    registro_completo: true,
    nombres: perfil.nombres,
    apellidos: perfil.apellidos,
  };
}

const sinPerfil = (id: number, nombre_usuario: string, rol: Usuario["rol"]): Usuario => ({
  id,
  nombre_usuario,
  email: null,
  rol,
  email_verificado: false,
  registro_completo: rol !== "admin",
  nombres: null,
  apellidos: null,
});

export const CUENTAS: CuentaMock[] = [
  { usuario: usuarioDe(laura), perfil: laura, activo: true },
  { usuario: usuarioDe(pedro), perfil: pedro, activo: true },
  { usuario: usuarioDe(carlos), perfil: carlos, activo: true },
  { usuario: sinPerfil(5, "jtorres", "admin"), activo: true },
  { usuario: sinPerfil(1, "root", "root"), activo: true },
  { usuario: { ...sinPerfil(2, "amejia", "admin"), registro_completo: true }, activo: false },
];

export const ADMINISTRADORES: Schemas["AdministradorSalida"][] = [
  {
    id: 3,
    nombre_usuario: "cruiz",
    nombres: "Carlos",
    apellidos: "Ruiz",
    estado: "activo",
    creado_en: "2026-09-02T15:20:00Z",
  },
  {
    id: 4,
    nombre_usuario: "mlopez",
    nombres: "María",
    apellidos: "López",
    estado: "activo",
    creado_en: "2026-09-05T13:05:00Z",
  },
  {
    id: 5,
    nombre_usuario: "jtorres",
    nombres: null,
    apellidos: null,
    estado: "registro_incompleto",
    creado_en: "2026-09-29T21:40:00Z",
  },
  {
    id: 2,
    nombre_usuario: "amejia",
    nombres: "Andrés",
    apellidos: "Mejía",
    estado: "inactivo",
    creado_en: "2026-08-12T14:00:00Z",
  },
];

/** HU-09: lo que impide desactivar la cuenta de lauragomez. */
export const BLOQUEOS_DESACTIVACION: Record<string, Schemas["BloqueoDesactivacion"][]> = {
  lauragomez: [
    {
      tipo: "compra",
      codigo_reserva: "K7Q2MX",
      vuelo_id: 88,
      vuelo_codigo: "STA-00088",
      origen: "Bogotá",
      destino: "Madrid",
      salida: "2026-12-11T03:00:00Z",
    },
  ],
};
