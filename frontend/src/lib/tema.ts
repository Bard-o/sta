/** Temas del sistema de diseño (design/tokens.json). El selector de la barra alterna entre los
 *  dos primeros; `dia` sigue disponible por atributo. */
export type Tema = "claro" | "noche" | "dia";

export const TEMA_POR_DEFECTO: Tema = "claro";
const CLAVE = "sta-tema";

const esTema = (valor: unknown): valor is Tema =>
  valor === "claro" || valor === "noche" || valor === "dia";

/** El tema que está aplicado en `<html>` (lo pone index.html antes de pintar). */
export function temaActual(): Tema {
  const aplicado = document.documentElement.dataset.theme;
  return esTema(aplicado) ? aplicado : TEMA_POR_DEFECTO;
}

/** Aplica el tema y lo recuerda en el navegador. Sin almacenamiento (modo privado) el cambio
 *  vale solo para la sesión de la pestaña. */
export function aplicarTema(tema: Tema) {
  document.documentElement.dataset.theme = tema;
  try {
    localStorage.setItem(CLAVE, tema);
  } catch {
    /* el cambio ya se aplicó; solo no se recuerda */
  }
}
