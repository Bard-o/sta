import { useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useSesion } from "@/auth/sesion";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { Pager } from "@/components/ui/pager";
import { hora } from "@/lib/format";
import type { VueloBusqueda } from "./buscar/api";
import { useIdas, useRegresos, useVuelosDelDiaDeRegreso } from "./buscar-ida-y-regreso/api";
import {
  busquedaCompleta,
  fechasDelTrayecto,
  leer,
  validarBusqueda,
  type Clase,
  type ErroresBusqueda,
} from "./buscar-ida-y-regreso/esquema";
import { FormularioTrayecto } from "./buscar-ida-y-regreso/formulario";
import { PaseElegible } from "./buscar-ida-y-regreso/pase-elegible";
import { ResumenTrayecto, type Perfil } from "./buscar-ida-y-regreso/resumen";
import { useCiudades } from "./programar-vuelo/api";

/** Clase con la que se elige un vuelo: económica, o primera si no quedan sillas en económica. */
const claseInicial = (v: VueloBusqueda): Clase => (v.economica.agotada ? "primera" : "economica");

/** `rango_invalido` del servidor: la fecha de regreso anterior a la de ida llega como `fecha`. */
function erroresDelServidor(error: unknown): ErroresBusqueda {
  if (!(error instanceof ApiError) || error.codigo !== "rango_invalido") return {};
  return error.campos.fecha ? { fecha_regreso: error.campos.fecha } : {};
}

/** S15 Búsqueda de ida y regreso (HU-21, HU-26). Pública. Dos pasos: se elige la ida y entonces
 *  solo se ofrecen regresos que salen después de su llegada. La clase se elige en cada tramo y el
 *  trayecto se agrega al carrito como una sola selección de dos tramos. */
export function BuscarIdaYRegresoPage() {
  const [params, setParams] = useSearchParams();
  const ubicacion = useLocation();
  const p = useMemo(() => leer(params), [params]);
  const [paginaIdas, setPaginaIdas] = useState(1);

  const { data: sesion } = useSesion();
  const perfil: Perfil = !sesion ? "visitante" : sesion.rol === "cliente" ? "cliente" : "personal";
  const { data: ciudades = [] } = useCiudades();
  const nombre = (codigo: string) => ciudades.find((c) => c.codigo === codigo)?.nombre ?? codigo;

  const completa = busquedaCompleta(p);
  const propios = completa ? validarBusqueda(p) : {};
  const valida = completa && Object.keys(propios).length === 0;

  const idas = useIdas(p, valida, paginaIdas);
  const ida = idas.data?.items.find((v) => v.id === Number(p.ida)) ?? null;
  const regresos = useRegresos(p, ida?.id ?? null);
  const delDia = useVuelosDelDiaDeRegreso(p, ida?.destino.codigo ?? null);
  const regreso = regresos.data?.items.find((v) => v.id === Number(p.regreso_id)) ?? null;
  const errores: ErroresBusqueda = { ...erroresDelServidor(regresos.error), ...propios };

  // Los que salen antes de la llegada de la ida no son regresos; se dibujan deshabilitados.
  const antesDeLlegar = useMemo(() => {
    if (!ida || !regresos.data) return [];
    const ofrecidos = new Set(regresos.data.items.map((v) => v.id));
    return (delDia.data?.items ?? []).filter(
      (v) => !ofrecidos.has(v.id) && Date.parse(v.salida) <= Date.parse(ida.llegada),
    );
  }, [ida, regresos.data, delDia.data]);

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

  function buscar(valores: Record<string, string>) {
    // Si cambian solo la fecha o la ciudad de regreso, la ida elegida se conserva.
    const mismaIda =
      valores.origen === p.origen &&
      valores.destino === p.destino &&
      valores.fecha_ida === p.fecha_ida;
    setPaginaIdas(1);
    escribir({
      ...valores,
      ida: mismaIda ? p.ida : "",
      clase_ida: mismaIda ? p.clase_ida : "",
      regreso_id: "",
      clase_regreso: "",
    });
  }

  const elegirIda = (v: VueloBusqueda) =>
    escribir({ ida: String(v.id), clase_ida: claseInicial(v), regreso_id: "", clase_regreso: "" });
  const elegirRegreso = (v: VueloBusqueda) =>
    escribir({ regreso_id: String(v.id), clase_regreso: claseInicial(v) });

  const titulo = valida
    ? `${nombre(p.origen)} → ${nombre(p.destino)} → ${nombre(p.regreso)}`
    : "Ida y regreso";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="sta-between">
        <div>
          <h1 className="sta-h1">{titulo}</h1>
          <p className="sta-sub">
            {valida ? `${fechasDelTrayecto(p)} ` : ""}El regreso puede llegar a otra ciudad. Solo
            mostramos regresos que salen después de tu llegada.
          </p>
        </div>
        <Button icon="search" href="/buscar">
          Solo ida
        </Button>
      </div>

      <FormularioTrayecto
        key={params.toString()}
        aplicados={p}
        errores={errores}
        onBuscar={buscar}
      />

      {!valida && (
        <p className="body sta-muted">
          Indica las ciudades y las fechas para ver los vuelos de ida.
        </p>
      )}

      {valida && (
        <div className="flex flex-col gap-6 lg:flex-row">
          <section className="flex min-w-0 flex-1 flex-col gap-3" aria-label="Vuelos de ida">
            <h2 className="sta-panel-title">1. Elige tu ida</h2>
            {idas.isPending && (
              <p role="status" className="body sta-muted">
                Buscando vuelos de ida…
              </p>
            )}
            {idas.isError && <Notice tone="danger">{idas.error.message}</Notice>}
            {idas.data && idas.data.items.length === 0 && (
              <Notice tone="info">
                No hay vuelos de {nombre(p.origen)} a {nombre(p.destino)} ese día. Cambia la fecha o
                las ciudades.
              </Notice>
            )}
            {idas.data?.items.map((v) => (
              <PaseElegible
                key={v.id}
                tramo="ida"
                vuelo={v}
                elegido={v.id === ida?.id}
                clase={v.id === ida?.id ? (p.clase_ida as Clase | "") : ""}
                onElegir={() => elegirIda(v)}
                onClase={(clase) => escribir({ clase_ida: clase })}
              />
            ))}
            {idas.data && (
              <Pager
                pagina={idas.data.pagina}
                total={idas.data.total}
                porPagina={idas.data.por_pagina}
                onChange={setPaginaIdas}
              />
            )}
          </section>

          <section className="flex min-w-0 flex-1 flex-col gap-3" aria-label="Vuelos de regreso">
            <h2 className="sta-panel-title">2. Elige tu regreso</h2>
            {!ida && (
              <Notice tone="info">
                Elige primero tu ida: solo ofrecemos regresos que salen después de tu llegada.
              </Notice>
            )}
            {ida && regresos.isPending && (
              <p role="status" className="body sta-muted">
                Buscando regresos…
              </p>
            )}
            {regresos.isError && Object.keys(erroresDelServidor(regresos.error)).length === 0 && (
              <Notice tone="danger">{regresos.error.message}</Notice>
            )}
            {ida && regresos.data && regresos.data.items.length === 0 && (
              <Glass title="No hay regresos para esa fecha">
                <p className="body sta-muted">
                  No hay vuelos de {nombre(ida.destino.codigo)} a {nombre(p.regreso)} después de tu
                  llegada. Cambia la fecha o la ciudad de regreso en el formulario: tu ida se
                  conserva.
                </p>
              </Glass>
            )}
            {regresos.data?.items.map((v) => (
              <PaseElegible
                key={v.id}
                tramo="regreso"
                vuelo={v}
                elegido={v.id === regreso?.id}
                clase={v.id === regreso?.id ? (p.clase_regreso as Clase | "") : ""}
                onElegir={() => elegirRegreso(v)}
                onClase={(clase) => escribir({ clase_regreso: clase })}
              />
            ))}
            {ida &&
              antesDeLlegar.map((v) => (
                <PaseElegible
                  key={v.id}
                  tramo="regreso"
                  vuelo={v}
                  elegido={false}
                  clase=""
                  motivoNoElegible={`Sale a las ${hora(v.salida, v.origen.zona_horaria)}, antes de tu llegada a ${nombre(ida.destino.codigo)}`}
                  onElegir={() => undefined}
                  onClase={() => undefined}
                />
              ))}
          </section>
        </div>
      )}

      {ida && regreso && p.clase_ida && p.clase_regreso && (
        <ResumenTrayecto
          ida={ida}
          claseIda={p.clase_ida as Clase}
          regreso={regreso}
          claseRegreso={p.clase_regreso as Clase}
          viajeros={Number(p.viajeros)}
          perfil={perfil}
          rutaLogin={ubicacion.pathname + ubicacion.search}
        />
      )}
    </div>
  );
}
