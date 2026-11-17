// Módulo carrito (HU-22, HU-23). Solo cliente. Cada lectura recalcula precio, cupo, límite y
// plazo. STA-00157 (económica) y STA-00158 (primera) están agotadas; STA-00159 tiene una silla
// en económica; lauragomez ya tiene 5 tiquetes en STA-00135 (limite_tiquetes).
import type { Schemas } from "@/api/client";
import { cop } from "@/lib/format";
import { type SeleccionGuardada, vueloViaje } from "../datos-viajes";
import {
  conPromociones,
  db,
  error,
  exigirRol,
  nuevoId,
  precioVigente,
  sesion,
  tiquetesActivos,
  vueloDetalle,
  vuelosDeTramos,
} from "../estado";
import { http } from "../http";
import {
  aLaVenta,
  type Clase,
  MAX_TIQUETES,
  NOMBRE_CLASE,
  venceEn,
  VIGENCIA_RESERVA_MIN,
} from "../reglas";
import { aIso } from "../tiempo";

type Aviso = Schemas["AvisoSeleccion"];

const usuarioId = () => sesion.get()!.id;
const noExiste = () => error(404, "no_encontrado", "La selección no existe.");
const delCliente = (id: number) =>
  db.selecciones.find((s) => s.id === id && s.usuario_id === usuarioId());

/** Límite de 5 y cupo, en el orden del contrato (HU-22). */
function validarCupo(tramos: { vuelo_id: number; clase: Clase }[], viajeros: number) {
  const vuelos = vuelosDeTramos(tramos.map((t) => t.vuelo_id));
  if (vuelos instanceof Response) return vuelos;
  for (const [i, t] of tramos.entries()) {
    const v = vuelos[i];
    const activos = tiquetesActivos(usuarioId(), v.id);
    if (activos + viajeros > MAX_TIQUETES) {
      return error(
        409,
        "limite_tiquetes",
        `Un cliente puede tener máximo ${MAX_TIQUETES} tiquetes activos en el mismo vuelo.`,
      );
    }
    if (v.ocupacion[t.clase].disponibles < viajeros) {
      return error(409, "clase_agotada", "No quedan sillas suficientes en esta clase.");
    }
  }
  return vuelos;
}

function aSeleccion(s: SeleccionGuardada): Schemas["SeleccionCarrito"] {
  const avisos: Aviso[] = [];
  const vuelos = s.tramos.map((t) => db.vuelos.find((v) => v.id === t.vuelo_id)!);
  const tramos = s.tramos.map((t, tramo): Schemas["TramoCarrito"] => {
    const v = vuelos[tramo];
    const detalle = vueloDetalle(conPromociones(v))[t.clase];
    const activos = tiquetesActivos(s.usuario_id, v.id);
    if (v.estado !== "programado") {
      avisos.push({
        codigo: "vuelo_no_disponible",
        tramo,
        mensaje: `${v.codigo} ya no está a la venta: se canceló o ya se realizó.`,
      });
    } else if (!aLaVenta(v)) {
      avisos.push({
        codigo: "fuera_de_plazo",
        tramo,
        mensaje: `La venta de ${v.codigo} ya cerró.`,
      });
    } else {
      if (detalle.precio_vigente !== t.precio_al_agregar) {
        avisos.push({
          codigo: "precio_cambio",
          tramo,
          mensaje: `El precio cambió de ${cop(t.precio_al_agregar)} a ${cop(detalle.precio_vigente)}. Pagarás el precio nuevo.`,
        });
      }
      if (activos + s.viajeros > MAX_TIQUETES) {
        avisos.push({
          codigo: "limite_tiquetes",
          tramo,
          mensaje: `Ya tienes ${activos} tiquetes activos en ${v.codigo} y el máximo por vuelo es ${MAX_TIQUETES}.`,
        });
      }
      if (detalle.disponibles < s.viajeros) {
        avisos.push({
          codigo: "clase_agotada",
          tramo,
          mensaje: `Ya no quedan sillas suficientes en ${NOMBRE_CLASE[t.clase]}. Cambia de clase o quita este vuelo.`,
        });
      }
    }
    return {
      vuelo: vueloViaje(v),
      clase: t.clase,
      precio_unitario: detalle.precio_vigente,
      precio_al_agregar: t.precio_al_agregar,
      promocion_porcentaje: detalle.promocion?.porcentaje ?? null,
      disponibles: detalle.disponibles,
      tiquetes_activos: activos,
    };
  });
  const confirmable = avisos.every((a) => a.codigo === "precio_cambio");
  return {
    id: s.id,
    tramos,
    viajeros: s.viajeros,
    subtotal: tramos.reduce((suma, t) => suma + t.precio_unitario * s.viajeros, 0),
    confirmable,
    avisos,
    reserva_venceria_en: confirmable ? venceEn(vuelos, VIGENCIA_RESERVA_MIN) : null,
    agregada_en: s.agregada_en,
  };
}

export const carritoHandlers = [
  http.get("/api/v1/carrito", ({ response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const selecciones = db.selecciones
      .filter((s) => s.usuario_id === usuarioId())
      .sort((a, b) => b.agregada_en.localeCompare(a.agregada_en))
      .map(aSeleccion);
    return response(200).json({
      selecciones,
      cantidad: selecciones.length,
      total: selecciones.filter((s) => s.confirmable).reduce((suma, s) => suma + s.subtotal, 0),
    });
  }),

  http.delete("/api/v1/carrito", ({ response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    db.selecciones = db.selecciones.filter((s) => s.usuario_id !== usuarioId());
    return response(204).empty();
  }),

  http.post("/api/v1/carrito/selecciones", async ({ request, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const vuelos = validarCupo(datos.tramos, datos.viajeros);
    if (vuelos instanceof Response) return response.untyped(vuelos);
    const nueva: SeleccionGuardada = {
      id: nuevoId(),
      usuario_id: usuarioId(),
      viajeros: datos.viajeros,
      agregada_en: aIso(new Date()),
      tramos: datos.tramos.map((t, i) => ({
        ...t,
        precio_al_agregar: precioVigente(vuelos[i], t.clase),
      })),
    };
    db.selecciones.push(nueva);
    return response(201).json(aSeleccion(nueva));
  }),

  http.patch(
    "/api/v1/carrito/selecciones/{seleccion_id}",
    async ({ params, request, response }) => {
      const bloqueo = exigirRol(["cliente"]);
      if (bloqueo) return response.untyped(bloqueo);
      const seleccion = delCliente(Number(params.seleccion_id));
      if (!seleccion) return response.untyped(noExiste());
      const datos = await request.json();
      const clases = datos.clases ?? seleccion.tramos.map((t) => t.clase);
      if (clases.length !== seleccion.tramos.length) {
        return response.untyped(
          error(422, "datos_invalidos", "Revisa los campos marcados.", {
            clases: "Debe traer una clase por cada tramo.",
          }),
        );
      }
      const viajeros = datos.viajeros ?? seleccion.viajeros;
      const tramos = seleccion.tramos.map((t, i) => ({ vuelo_id: t.vuelo_id, clase: clases[i] }));
      const vuelos = validarCupo(tramos, viajeros);
      if (vuelos instanceof Response) return response.untyped(vuelos);
      seleccion.viajeros = viajeros;
      seleccion.tramos = tramos.map((t, i) => ({
        ...t,
        precio_al_agregar: precioVigente(vuelos[i], t.clase),
      }));
      return response(200).json(aSeleccion(seleccion));
    },
  ),

  http.delete("/api/v1/carrito/selecciones/{seleccion_id}", ({ params, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const seleccion = delCliente(Number(params.seleccion_id));
    if (!seleccion) return response.untyped(noExiste());
    db.selecciones = db.selecciones.filter((s) => s !== seleccion);
    return response(204).empty();
  }),
];
