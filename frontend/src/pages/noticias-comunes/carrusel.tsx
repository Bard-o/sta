import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { cop, fecha, hora } from "@/lib/format";
import { CiudadImagen } from "./ciudad-imagen";
import { MAX_CARRUSEL } from "./api";
import { esVigente, NOMBRE_CLASE, precioDeNoticia, type Noticia } from "./estado";

/** Carrusel bajo la barra de navegación (HU-19): como máximo 10 elementos, solo vigentes, en el
 *  orden que manda el servidor (promociones vigentes primero). Sin movimiento automático. */
export function Carrusel({ noticias }: { noticias: Noticia[] }) {
  const items = noticias.filter(esVigente).slice(0, MAX_CARRUSEL);
  const [indice, setIndice] = useState(0);
  if (items.length === 0) return null;

  const actual = Math.min(indice, items.length - 1);
  const n = items[actual];
  const precio = precioDeNoticia(n);
  const zona = n.origen.zona_horaria;
  const promocion = n.tipo === "promocion";

  return (
    <Glass
      as="section"
      padded={false}
      aria-roledescription="carrusel"
      aria-label="Ofertas y vuelos nuevos"
    >
      <div aria-live="polite" className="grid gap-0 md:grid-cols-2">
        <CiudadImagen
          src={n.imagen_url}
          codigo={n.destino.codigo}
          nombre={n.destino.nombre}
          className="h-48 w-full rounded-b-none md:h-full md:min-h-56 md:rounded-r-none"
        />
        <div className="flex flex-col items-start gap-3 p-5">
          <Badge tone={promocion ? "accent" : "neutral"}>
            {promocion ? "Promoción vigente" : "Vuelo nuevo"}
          </Badge>
          <h2 className="title-lg">
            {n.origen.nombre} → {n.destino.nombre}
          </h2>
          <p className="body">
            Salida {fecha(n.salida, zona)}, {hora(n.salida, zona)}. {NOMBRE_CLASE[precio.clase]}{" "}
            {precio.anterior !== undefined && (
              <s className="sta-pass__old">{cop(precio.anterior)}</s>
            )}{" "}
            <strong className="sta-num">{cop(precio.actual)}</strong>
          </p>
          <div className="sta-row">
            <Button variant="primary" href={`/vuelos/${n.vuelo_id}`}>
              Ver vuelo
            </Button>
            <span className="caption sta-muted">
              {actual + 1} de {items.length}
            </span>
          </div>
        </div>
      </div>
      {items.length > 1 && (
        <div className="sta-row justify-center pb-3">
          <Button
            size="sm"
            variant="ghost"
            aria-label="Elemento anterior"
            onClick={() => setIndice((actual - 1 + items.length) % items.length)}
          >
            Anterior
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Elemento siguiente"
            onClick={() => setIndice((actual + 1) % items.length)}
          >
            Siguiente
          </Button>
        </div>
      )}
    </Glass>
  );
}
