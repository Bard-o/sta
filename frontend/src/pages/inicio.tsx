import { Glass } from "@/components/ui/glass";

/** Página pública de inicio (visitante). La búsqueda y el carrusel llegan con sus issues. */
export function InicioPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="sta-h1">Tiquetes aéreos AVIANCO</h1>
        <p className="sta-sub">Busca vuelos, revisa las noticias y haz tu check-in.</p>
      </div>
      <Glass title="Próximamente">
        <p className="body">Aquí estará la búsqueda de vuelos.</p>
      </Glass>
    </div>
  );
}
