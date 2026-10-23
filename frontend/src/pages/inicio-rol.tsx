import { NOMBRE_ROL } from "@/auth/roles";
import { useSesion } from "@/auth/sesion";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";

/** Página de inicio de cada rol. Cada módulo la llena en su propio issue. */
export function InicioRolPage() {
  const { data: usuario } = useSesion();
  if (!usuario) return null;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="sta-h1">Hola, {usuario.nombre_usuario}</h1>
        <p className="sta-sub">Entraste como {NOMBRE_ROL[usuario.rol].toLowerCase()}.</p>
      </div>
      <Glass title="Tu sesión">
        <p className="body">Usa el menú de arriba para ir a las funciones de tu rol.</p>
        {usuario.rol === "admin" && (
          <div className="mt-4">
            <Button variant="primary" href="/admin/vuelos/nuevo">
              Programar vuelo
            </Button>
          </div>
        )}
      </Glass>
    </div>
  );
}
