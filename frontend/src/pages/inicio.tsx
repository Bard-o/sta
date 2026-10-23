import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { useCarrusel, useNoticias } from "./noticias-comunes/api";
import { Carrusel } from "./noticias-comunes/carrusel";
import { NoticiaItem } from "./noticias-comunes/noticia-item";

const NOTICIAS_EN_INICIO = 5;

/** S13 · Inicio público (HU-19): carrusel bajo la barra y las últimas noticias. Sin sesión. */
export function InicioPage() {
  const carrusel = useCarrusel();
  const noticias = useNoticias(1, NOTICIAS_EN_INICIO);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="sta-h1">Tiquetes aéreos AVIANCO</h1>
        <p className="sta-sub">Conoce los vuelos nuevos y las promociones de la aerolínea.</p>
      </div>

      {carrusel.isError ? (
        <Notice tone="danger">
          No pudimos cargar las ofertas destacadas.{" "}
          <Button size="sm" variant="ghost" onClick={() => void carrusel.refetch()}>
            Reintentar
          </Button>
        </Notice>
      ) : (
        carrusel.data && <Carrusel noticias={carrusel.data} />
      )}

      <Glass title="Noticias">
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
            <p className="mt-2">
              <Link className="sta-link" to="/noticias">
                Ver todas las noticias
              </Link>
            </p>
          </>
        )}
      </Glass>
    </div>
  );
}
