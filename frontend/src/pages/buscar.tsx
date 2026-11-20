import { useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useCarrito } from "@/auth/carrito";
import { useSesion } from "@/auth/sesion";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { Pager } from "@/components/ui/pager";
import { POR_PAGINA, useBuscarVuelos } from "./buscar/api";
import {
  CLAVES_FILTRO,
  hayFiltros,
  leerFiltros,
  leerOrden,
  leerPagina,
  ORDENES,
  resumenDeFiltros,
  validarRangos,
  type Clase,
  type Filtros,
  type Orden,
} from "./buscar/filtros";
import { FiltrosBusqueda, type ErroresFiltros } from "./buscar/filtros-busqueda";
import { ResultadoVuelo, type Perfil } from "./buscar/resultado";
import { useCiudades } from "./programar-vuelo/api";

/** Errores de rango (`rango_invalido`) que devolvió el servidor, por filtro. */
function erroresDelServidor(error: unknown): ErroresFiltros {
  if (!(error instanceof ApiError) || error.codigo !== "rango_invalido") return {};
  const errores: ErroresFiltros = {};
  for (const [campo, mensaje] of Object.entries(error.campos)) {
    if ((CLAVES_FILTRO as readonly string[]).includes(campo)) {
      errores[campo as keyof ErroresFiltros] = mensaje;
    } else if (campo === "hora_hasta") {
      errores.franja = mensaje;
    }
  }
  return errores;
}

/** S14 Resultados de búsqueda (HU-20, HU-22). Pública: el visitante busca y, al agregar, inicia
 *  sesión. Los filtros, el orden y la página viven en la dirección. */
export function BuscarPage() {
  const [params, setParams] = useSearchParams();
  const ubicacion = useLocation();
  const filtros = useMemo(() => leerFiltros(params), [params]);
  const orden = leerOrden(params);
  const pagina = leerPagina(params);

  // En pantallas angostas los filtros arrancan plegados para que los resultados queden a la vista.
  const [filtrosAbiertos, setFiltrosAbiertos] = useState(false);
  const { data: sesion } = useSesion();
  const perfil: Perfil = !sesion ? "visitante" : sesion.rol === "cliente" ? "cliente" : "personal";
  const { data: carrito } = useCarrito(perfil === "cliente");
  const enCarrito = useMemo(
    () => new Set(carrito?.selecciones.flatMap((s) => s.tramos.map((t) => t.vuelo.id))),
    [carrito],
  );
  const { data: ciudades = [] } = useCiudades();
  const nombreCiudad = (codigo: string) =>
    ciudades.find((c) => c.codigo === codigo)?.nombre ?? codigo;

  // Un rango que la pantalla ya ve inválido no se envía; el servidor igual lo valida (RNF).
  const propios = validarRangos(filtros);
  const rangoInvalido = Object.keys(propios).length > 0;
  const consulta = useBuscarVuelos(filtros, orden, pagina, !rangoInvalido);
  const errores: ErroresFiltros = { ...erroresDelServidor(consulta.error), ...propios };
  const otroError =
    consulta.isError && Object.keys(erroresDelServidor(consulta.error)).length === 0;

  const resultados = consulta.data?.items ?? [];
  const total = consulta.data?.total ?? 0;
  const resumen = resumenDeFiltros(filtros, nombreCiudad);
  const activos = CLAVES_FILTRO.filter((clave) => filtros[clave] !== "").length;
  const clase = (filtros.clase || undefined) as Clase | undefined;

  function escribir(cambios: Record<string, string>) {
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

  const aplicar = (nuevos: Filtros) => escribir({ ...nuevos, pagina: "" });
  const limpiar = () => setParams({}, { replace: true });
  const cambiarOrden = (valor: Orden) =>
    escribir({ orden: valor === "precio" ? "" : valor, pagina: "" });

  const titulo = consulta.data
    ? `${total} ${total === 1 ? "vuelo" : "vuelos"}${filtros.origen ? ` desde ${nombreCiudad(filtros.origen)}` : ""}`
    : "Buscar vuelos";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 lg:flex-row">
      <aside className="w-full lg:w-72 lg:shrink-0">
        <Button
          className="w-full lg:hidden"
          icon="sliders"
          aria-expanded={filtrosAbiertos}
          aria-controls="filtros-busqueda"
          onClick={() => setFiltrosAbiertos((abiertos) => !abiertos)}
        >
          {filtrosAbiertos ? "Ocultar filtros" : "Mostrar filtros"}
          {activos > 0 && ` (${activos})`}
        </Button>
        <div id="filtros-busqueda" className={filtrosAbiertos ? "mt-4 block" : "hidden lg:block"}>
          <FiltrosBusqueda
            // Se vuelve a armar el borrador si los filtros cambian desde fuera (Quitar filtros, atrás).
            key={params.toString()}
            aplicados={filtros}
            errores={errores}
            onAplicar={aplicar}
            onLimpiar={limpiar}
          />
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col gap-4" aria-label="Resultados">
        <div className="sta-between">
          <div>
            <h1 className="sta-h1">{titulo}</h1>
            {resumen && <p className="sta-sub">{resumen}</p>}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {/* HU-21: la búsqueda de ida y regreso arranca desde aquí. */}
            <Button icon="plane" href="/buscar/ida-y-regreso">
              Ida y regreso
            </Button>
            <Field
              label="Ordenar por"
              options={ORDENES}
              value={orden}
              onChange={(e) => cambiarOrden(e.target.value as Orden)}
            />
          </div>
        </div>

        {rangoInvalido && <Notice tone="danger">Revisa los rangos marcados en los filtros.</Notice>}
        {otroError && <Notice tone="danger">{consulta.error?.message}</Notice>}
        {consulta.isPending && !rangoInvalido && (
          <p role="status" className="body sta-muted">
            Buscando vuelos…
          </p>
        )}

        {consulta.data && resultados.length === 0 && (
          <Glass title="No encontramos vuelos">
            <div className="flex flex-col items-start gap-4">
              <p className="body sta-muted">
                {hayFiltros(filtros)
                  ? "Ningún vuelo cumple todos los filtros. Cambia alguno o quítalos para ver más."
                  : "Todavía no hay vuelos a la venta."}
              </p>
              {hayFiltros(filtros) && <Button onClick={limpiar}>Quitar filtros</Button>}
            </div>
          </Glass>
        )}

        {resultados.map((vuelo) => (
          <ResultadoVuelo
            key={vuelo.id}
            vuelo={vuelo}
            clase={clase}
            perfil={perfil}
            enCarrito={enCarrito.has(vuelo.id)}
            rutaLogin={ubicacion.pathname + ubicacion.search}
          />
        ))}

        {consulta.data && (
          <Pager
            pagina={consulta.data.pagina}
            total={total}
            porPagina={POR_PAGINA}
            onChange={(p) => escribir({ pagina: p === 1 ? "" : String(p) })}
          />
        )}
      </section>
    </div>
  );
}
