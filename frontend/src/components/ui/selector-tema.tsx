import { useState } from "react";
import { aplicarTema, temaActual, type Tema } from "@/lib/tema";
import { Button } from "./button";

/** Alterna entre el tema claro y Noche. El botón dice a qué tema cambia. */
export function SelectorTema() {
  const [tema, setTema] = useState<Tema>(temaActual);
  const aNoche = tema !== "noche";

  const cambiar = () => {
    const siguiente: Tema = aNoche ? "noche" : "claro";
    aplicarTema(siguiente);
    setTema(siguiente);
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      icon={aNoche ? "moon" : "sun"}
      onClick={cambiar}
      aria-label={aNoche ? "Cambiar al tema noche" : "Cambiar al tema claro"}
      title={aNoche ? "Tema noche" : "Tema claro"}
    />
  );
}
