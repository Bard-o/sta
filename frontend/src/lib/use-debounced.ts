import { useEffect, useState } from "react";

/** Devuelve `valor` solo cuando deja de cambiar durante `espera` ms (evita una petición por tecla). */
export function useDebounced<T>(valor: T, espera = 400): T {
  const [estable, setEstable] = useState(valor);
  useEffect(() => {
    const id = setTimeout(() => setEstable(valor), espera);
    return () => clearTimeout(id);
  }, [valor, espera]);
  return estable;
}
