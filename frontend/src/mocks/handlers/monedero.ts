// Módulo monedero (HU-28 a HU-31). Solo cliente. 4242424242424241 no pasa Luhn; un vencimiento
// anterior al mes actual está vencido; la tarjeta 23 de lauragomez (**** 1111) venció en 05/26.
import type { Schemas } from "@/api/client";
import type { TarjetaGuardada } from "../datos-monedero";
import {
  aMovimiento,
  db,
  error,
  exigirRol,
  nuevoId,
  paginar,
  registrarMovimiento,
  saldoDe,
  sesion,
} from "../estado";
import { http } from "../http";
import { fechaLocal, franquiciaDe, pasaLuhn, tarjetaVencida, ZONA_COLOMBIA } from "../reglas";
import { aIso } from "../tiempo";

const usuarioId = () => sesion.get()!.id;
const noExiste = () => error(404, "no_encontrado", "La tarjeta no existe.");
const deCliente = (id: number) =>
  db.tarjetas.find((t) => t.id === id && t.usuario_id === usuarioId() && !t.eliminada);

function aTarjeta({ usuario_id, eliminada, ...t }: TarjetaGuardada): Schemas["Tarjeta"] {
  void usuario_id;
  void eliminada;
  return { ...t, vencida: tarjetaVencida(t.vencimiento) };
}

export const monederoHandlers = [
  http.get("/api/v1/monedero", ({ response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    return response(200).json({ saldo: saldoDe(usuarioId()) });
  }),

  http.get("/api/v1/monedero/movimientos", ({ request, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const q = new URL(request.url).searchParams;
    const [tipo, desde, hasta] = [q.get("tipo"), q.get("desde"), q.get("hasta")];
    if (desde && hasta && hasta < desde) {
      return response.untyped(
        error(422, "rango_invalido", "Revisa los rangos marcados.", {
          hasta: "La fecha final no puede ser anterior a la inicial.",
        }),
      );
    }
    const items = db.movimientos
      .filter((m) => m.usuario_id === usuarioId() && (!tipo || m.tipo === tipo))
      .filter((m) => {
        const dia = fechaLocal(m.creado_en, ZONA_COLOMBIA);
        return (!desde || dia >= desde) && (!hasta || dia <= hasta);
      })
      .sort((a, b) => b.creado_en.localeCompare(a.creado_en) || b.id - a.id)
      .map(aMovimiento);
    return response(200).json(paginar(items, q.get("pagina"), q.get("por_pagina")));
  }),

  http.get("/api/v1/monedero/tarjetas", ({ response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const tarjetas = db.tarjetas
      .filter((t) => t.usuario_id === usuarioId() && !t.eliminada)
      .sort((a, b) => b.creada_en.localeCompare(a.creada_en))
      .map(aTarjeta);
    return response(200).json(tarjetas);
  }),

  http.post("/api/v1/monedero/tarjetas", async ({ request, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const campos: Record<string, string> = {};
    if (!/^\d{13,19}$/.test(datos.numero ?? "")) campos.numero = "El formato no es válido.";
    if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(datos.vencimiento ?? ""))
      campos.vencimiento = "El formato no es válido.";
    if (!/^\d{3,4}$/.test(datos.cvv ?? "")) campos.cvv = "El formato no es válido.";
    if (!datos.titular?.trim()) campos.titular = "Este campo es obligatorio.";
    if (Object.keys(campos).length > 0) {
      return response.untyped(error(422, "datos_invalidos", "Revisa los campos marcados.", campos));
    }
    if (!pasaLuhn(datos.numero)) {
      return response.untyped(
        error(422, "tarjeta_invalida", "Revisa los datos de la tarjeta.", {
          numero: "El número no es válido. Revisa los dígitos.",
        }),
      );
    }
    if (tarjetaVencida(datos.vencimiento)) {
      return response.untyped(
        error(422, "tarjeta_vencida", "La tarjeta está vencida.", {
          vencimiento: "La tarjeta está vencida.",
        }),
      );
    }
    // RNF-12: solo se guardan los últimos 4 dígitos; el número y el CVV se descartan.
    const nueva: TarjetaGuardada = {
      id: nuevoId(),
      usuario_id: usuarioId(),
      eliminada: false,
      tipo: datos.tipo,
      franquicia: franquiciaDe(datos.numero),
      titular: datos.titular.trim(),
      numero_enmascarado: `**** ${datos.numero.slice(-4)}`,
      vencimiento: datos.vencimiento,
      creada_en: aIso(new Date()),
    };
    db.tarjetas.push(nueva);
    return response(201).json(aTarjeta(nueva));
  }),

  http.delete("/api/v1/monedero/tarjetas/{tarjeta_id}", ({ params, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const tarjeta = deCliente(Number(params.tarjeta_id));
    if (!tarjeta) return response.untyped(noExiste());
    tarjeta.eliminada = true; // borrado lógico: las recargas conservan su referencia
    return response(204).empty();
  }),

  http.post("/api/v1/monedero/recargas", async ({ request, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    if (!Number.isInteger(datos.valor) || datos.valor <= 0) {
      return response.untyped(
        error(422, "datos_invalidos", "Revisa los campos marcados.", {
          valor: "Debe ser mayor que 0.",
        }),
      );
    }
    const tarjeta = deCliente(datos.tarjeta_id);
    if (!tarjeta) return response.untyped(noExiste());
    if (tarjetaVencida(tarjeta.vencimiento)) {
      return response.untyped(
        error(422, "tarjeta_vencida", "La tarjeta está vencida.", {
          tarjeta_id: "La tarjeta está vencida. Elige otra o registra una nueva.",
        }),
      );
    }
    const movimiento = registrarMovimiento(
      usuarioId(),
      "recarga",
      datos.valor,
      tarjeta.numero_enmascarado,
    );
    return response(201).json(aMovimiento(movimiento));
  }),
];
