import { Link } from "react-router";
import { Badge } from "@/components/ui/badge";
import { cop, fechaRelativa } from "@/lib/format";
import { CiudadImagen } from "./ciudad-imagen";
import {
  esVigente,
  etiquetaDeNoticia,
  NOMBRE_CLASE,
  precioDeNoticia,
  type Noticia,
} from "./estado";

/** Una noticia del listado: imagen, fecha, estado y título. Abre el detalle del vuelo (HU-19).
 *  Las que ya no están vigentes se muestran atenuadas y con su estado escrito. */
export function NoticiaItem({ noticia }: { noticia: Noticia }) {
  const etiqueta = etiquetaDeNoticia(noticia);
  const vigente = esVigente(noticia);
  const precio = precioDeNoticia(noticia);
  return (
    <li className="flex gap-4 py-3">
      <CiudadImagen
        src={noticia.imagen_url}
        codigo={noticia.destino.codigo}
        nombre={noticia.destino.nombre}
        className="h-16 w-24 shrink-0"
      />
      <div className={vigente ? "flex flex-col gap-1" : "flex flex-col gap-1 opacity-70"}>
        <div className="caption sta-muted sta-row">
          <span>{fechaRelativa(noticia.publicada_en)}</span>
          {etiqueta && <Badge tone={etiqueta.tone}>{etiqueta.label}</Badge>}
        </div>
        <Link className="body-strong sta-link" to={`/vuelos/${noticia.vuelo_id}`}>
          {noticia.titulo}
        </Link>
        <span className="caption sta-muted">
          {NOMBRE_CLASE[precio.clase]}{" "}
          {precio.anterior !== undefined && <s className="sta-pass__old">{cop(precio.anterior)}</s>}{" "}
          <span className="sta-num">{cop(precio.actual)}</span>
        </span>
      </div>
    </li>
  );
}
