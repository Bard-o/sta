import { useSearchParams } from "react-router";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { Pager } from "@/components/ui/pager";
import { Button } from "@/components/ui/button";
import { NOTICIAS_POR_PAGINA, useNoticias } from "./noticias-comunes/api";
import { NoticiaItem } from "./noticias-comunes/noticia-item";

/** Todas las noticias, de la más reciente a la más antigua, con paginación (HU-19). Solo lectura:
 *  las noticias son automáticas y no hay interfaz para crearlas (RF-55). */
export function NoticiasPage() {
  const [params, setParams] = useSearchParams();
  const pedida = Number(params.get("pagina"));
  const pagina = Number.isInteger(pedida) && pedida >= 1 ? pedida : 1;
  const noticias = useNoticias(pagina);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="sta-h1">Noticias</h1>
        <p className="sta-sub">Vuelos nuevos y promociones, de la más reciente a la más antigua.</p>
      </div>

      <Glass>
        {noticias.isError ? (
          <Notice tone="danger">
            No pudimos cargar las noticias.{" "}
            <Button size="sm" variant="ghost" onClick={() => void noticias.refetch()}>
              Reintentar
            </Button>
          </Notice>
        ) : noticias.isPending ? (
          <p className="body sta-muted">Cargando noticias…</p>
        ) : noticias.data.items.length === 0 ? (
          <p className="body sta-muted">Todavía no hay noticias.</p>
        ) : (
          <>
            <ul className="divide-glass-edge divide-y">
              {noticias.data.items.map((n) => (
                <NoticiaItem key={n.id} noticia={n} />
              ))}
            </ul>
            <Pager
              className="mt-4"
              pagina={noticias.data.pagina}
              total={noticias.data.total}
              porPagina={noticias.data.por_pagina || NOTICIAS_POR_PAGINA}
              onChange={(p) => setParams(p === 1 ? {} : { pagina: String(p) })}
            />
          </>
        )}
      </Glass>
    </div>
  );
}
