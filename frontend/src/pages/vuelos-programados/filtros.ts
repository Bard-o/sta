import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

/** Filtros de los listados de vuelos (S09, S12): texto, rango de fechas y página, guardados en la
 *  dirección para poder recargar o compartir el enlace. El texto se aplica al dejar de escribir. */
export function useFiltros() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const desde = params.get("desde") ?? "";
  const hasta = params.get("hasta") ?? "";
  const pagina = Math.max(1, Number(params.get("pagina")) || 1);

  const [texto, setTexto] = useState(q);
  const temporizador = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(temporizador.current), []);

  /** Pone (o quita, si va vacío) parámetros de la dirección. */
  function cambiar(cambios: Record<string, string>) {
    setParams(
      (previos) => {
        const siguiente = new URLSearchParams(previos);
        for (const [clave, valor] of Object.entries(cambios)) {
          if (valor) siguiente.set(clave, valor);
          else siguiente.delete(clave);
        }
        return siguiente;
      },
      { replace: true },
    );
  }

  // `setParams` no encola: el temporizador debe usar el `cambiar` del último render, no el viejo.
  const cambiarActual = useRef(cambiar);
  useEffect(() => {
    cambiarActual.current = cambiar;
  });

  function escribir(valor: string) {
    setTexto(valor);
    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(
      () => cambiarActual.current({ q: valor.trim(), pagina: "" }),
      400,
    );
  }

  function limpiar() {
    clearTimeout(temporizador.current);
    setTexto("");
    setParams({}, { replace: true });
  }

  return {
    q,
    desde,
    hasta,
    pagina,
    texto,
    params,
    cambiar,
    escribir,
    limpiar,
    periodoInvalido: desde !== "" && hasta !== "" && hasta < desde,
    hayFiltros: q !== "" || desde !== "" || hasta !== "",
  };
}

export type Filtros = ReturnType<typeof useFiltros>;
