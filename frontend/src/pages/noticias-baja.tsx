import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useBajaNoticias } from "@/auth/suscripcion";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Icon } from "@/components/ui/icon";
import { Notice } from "@/components/ui/notice";

/** Baja de noticias desde el enlace de cada correo (HU-08). Pública: no pide iniciar sesión. */
export function BajaNoticiasPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const baja = useBajaNoticias();

  // Un solo envío aunque React monte el componente dos veces en desarrollo.
  const enviado = useRef(false);
  useEffect(() => {
    if (!token || enviado.current) return;
    enviado.current = true;
    baja.mutate(token);
  }, [token, baja]);

  const invalido =
    !token || (baja.error instanceof ApiError && baja.error.codigo === "enlace_invalido");

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6">
      <div>
        <h1 className="sta-h1">Noticias por correo</h1>
        <p className="sta-sub">Baja de la suscripción a vuelos nuevos y promociones.</p>
      </div>
      <Glass as="div">
        {baja.isSuccess ? (
          <>
            <p className="mb-4 flex items-start gap-2">
              <Icon name="check-circle" className="text-success" />
              <span>
                Listo, te diste de baja. Ya no recibirás correos de noticias. Puedes volver a
                suscribirte desde tu perfil.
              </span>
            </p>
            <Button variant="primary" href="/">
              Ir al inicio
            </Button>
          </>
        ) : invalido ? (
          <>
            <Notice tone="danger">
              Este enlace de baja no es válido. Si sigues recibiendo correos, puedes darte de baja
              desde tu perfil.
            </Notice>
            <Link className="sta-link" to="/perfil">
              Ir a mi perfil
            </Link>
          </>
        ) : baja.isError ? (
          <Notice tone="danger">{baja.error.message}</Notice>
        ) : (
          <p role="status" className="label sta-muted">
            Procesando tu baja…
          </p>
        )}
      </Glass>
    </div>
  );
}
