import { useEffect, useState } from "react";

/** La hora de ahora, renovada cada `cada` milisegundos: para «Vence en 5 h 12 min». */
export function useAhora(cada = 30_000): number {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setAhora(Date.now()), cada);
    return () => clearInterval(id);
  }, [cada]);
  return ahora;
}

/** «2 d 3 h», «5 h 12 min», «12 min» o «menos de 1 min»: lo que falta hasta `venceEn`. */
export function textoRestante(venceEn: string, ahora: number): string {
  const minutos = Math.floor((Date.parse(venceEn) - ahora) / 60_000);
  if (minutos < 1) return "menos de 1 min";
  const dias = Math.floor(minutos / 1440);
  const horas = Math.floor((minutos % 1440) / 60);
  const resto = minutos % 60;
  if (dias > 0) return horas > 0 ? `${dias} d ${horas} h` : `${dias} d`;
  if (horas > 0) return resto > 0 ? `${horas} h ${resto} min` : `${horas} h`;
  return `${resto} min`;
}
