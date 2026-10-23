import { useId } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { ApiError, type Schemas } from "@/api/client";
import { useSuscripcion } from "@/auth/suscripcion";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { Switch } from "@/components/ui/switch";

/** S05 · Correos que recibes (HU-08). Solo el cliente. Suscribirse exige el correo verificado;
 *  darse de baja siempre se permite. El correo semanal de recomendaciones llega en la iteración 4. */
export function Suscripcion({ perfil }: { perfil: Schemas["PerfilSalida"] }) {
  const suscripcion = useSuscripcion();
  const idTitulo = useId();
  const idAyuda = useId();

  const sinVerificar = !perfil.email_verificado;
  const error = suscripcion.error;
  const correoNoVerificado = error instanceof ApiError && error.codigo === "correo_no_verificado";
  const avisarVerificacion = sinVerificar || correoNoVerificado;

  const cambiar = (activar: boolean) =>
    suscripcion.mutate(activar, {
      onSuccess: ({ noticias }) =>
        toast.success(
          noticias
            ? "Te suscribiste a las noticias de vuelos y promociones."
            : "Te diste de baja de las noticias. Ya no te enviaremos esos correos.",
        ),
    });

  return (
    <Glass as="div" title="Correos que recibes">
      {avisarVerificacion && (
        <Notice tone="info">
          Verifica tu correo para suscribirte a noticias.{" "}
          <Link className="sta-link" to="/verificar-correo">
            Verificar correo
          </Link>
        </Notice>
      )}
      {error && !correoNoVerificado && <Notice tone="danger">{error.message}</Notice>}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p id={idTitulo} className="font-semibold">
            Noticias de vuelos y promociones
          </p>
          <p id={idAyuda} className="caption sta-muted">
            Te avisamos cada vuelo nuevo y cada promoción.
          </p>
        </div>
        <Switch
          aria-labelledby={idTitulo}
          aria-describedby={idAyuda}
          checked={perfil.suscrito_noticias}
          onCheckedChange={cambiar}
          // Se puede apagar siempre; encender exige el correo verificado.
          disabled={suscripcion.isPending || (sinVerificar && !perfil.suscrito_noticias)}
        />
      </div>
    </Glass>
  );
}
