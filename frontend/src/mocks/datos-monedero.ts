// Tarjetas y movimientos de la API simulada (docs/api/iteracion-2.md, «Mocks para el frontend»).
// Saldo de lauragomez: la suma de sus movimientos, $ 1.000.000.
import type { Schemas } from "@/api/client";

export type TarjetaGuardada = Omit<Schemas["Tarjeta"], "vencida"> & {
  usuario_id: number;
  eliminada: boolean;
};
export type MovimientoGuardado = Schemas["Movimiento"] & { usuario_id: number };

const LAURA = 12;
const titular = "LAURA GOMEZ RIOS";

export const TARJETAS: TarjetaGuardada[] = [
  {
    id: 21,
    usuario_id: LAURA,
    eliminada: false,
    tipo: "credito",
    franquicia: "visa",
    titular,
    numero_enmascarado: "**** 4242",
    vencimiento: "08/28",
    creada_en: "2026-09-29T15:05:00Z",
  },
  {
    id: 22,
    usuario_id: LAURA,
    eliminada: false,
    tipo: "debito",
    franquicia: "mastercard",
    titular,
    numero_enmascarado: "**** 5100",
    vencimiento: "01/27",
    creada_en: "2026-09-18T17:35:00Z",
  },
  {
    id: 23,
    usuario_id: LAURA,
    eliminada: false,
    tipo: "credito",
    franquicia: "visa",
    titular,
    numero_enmascarado: "**** 1111",
    vencimiento: "05/26",
    creada_en: "2025-06-01T12:00:00Z",
  },
];

const mov = (
  id: number,
  tipo: MovimientoGuardado["tipo"],
  valor: number,
  saldo_resultante: number,
  referencia: string,
  creado_en: string,
): MovimientoGuardado => ({
  id,
  usuario_id: LAURA,
  tipo,
  valor,
  saldo_resultante,
  referencia,
  creado_en,
});

export const MOVIMIENTOS: MovimientoGuardado[] = [
  mov(31, "recarga", 500_000, 500_000, "**** 5100", "2026-09-18T17:40:00Z"),
  mov(32, "compra", -185_000, 315_000, "Q8W2RT", "2026-09-20T13:02:00Z"),
  mov(33, "reembolso", 185_000, 500_000, "Q8W2RT", "2026-09-21T23:30:00Z"),
  mov(34, "recarga", 500_000, 1_000_000, "**** 4242", "2026-09-29T15:09:00Z"),
  mov(35, "recarga", 5_800_000, 6_800_000, "**** 4242", "2026-10-02T14:45:00Z"),
  mov(36, "compra", -4_900_000, 1_900_000, "K7Q2MX", "2026-10-02T15:00:00Z"),
  mov(37, "compra", -900_000, 1_000_000, "P3X7KD", "2026-11-03T16:20:00Z"),
];
