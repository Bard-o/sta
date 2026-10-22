import { useEffect, useRef } from "react";
import { Link, Navigate, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { inicioDe } from "@/auth/roles";
import { usePerfil } from "@/auth/perfil";
import { useSesion } from "@/auth/sesion";
import {
  RUTA_VERIFICACION,
  useReenviarVerificacion,
  useVerificarCorreo,
} from "@/auth/verificacion";
import { Button } from "@/components/ui/button";
import { Glass } from "@/components/ui/glass";
import { Icon } from "@/components/ui/icon";
import { Notice } from "@/components/ui/notice";

const ENLACE_VENCIDO =
  "Este enlace venció o ya fue usado. Pide uno nuevo para verificar tu correo.";

/** S02 · Verificación de correo (HU-02). Con `?token=` confirma el enlace del correo; sin él,
 *  muestra el estado de la cuenta y permite reenviar el enlace. */
export function VerificarCorreoPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  return token ? <ConfirmarEnlace token={token} /> : <EstadoDeLaCuenta />;
}

function Encabezado({ titulo, subtitulo }: { titulo: string; subtitulo: string }) {
  return (
    <div>
      <h1 className="sta-h1">{titulo}</h1>
      <p className="sta-sub">{subtitulo}</p>
    </div>
  );
}

/** Mensaje de lo que pasó al pedir un enlace nuevo. */
function ResultadoReenvio({
  reenvio,
  correo,
}: {
  reenvio: ReturnType<typeof useReenviarVerificacion>;
  correo?: string;
}) {
  if (reenvio.isSuccess) {
    return (
      <Notice tone="info">
        Te enviamos un enlace nuevo{correo ? ` a ${correo}` : ""}. Vence en 24 horas y el anterior
        ya no funciona.
      </Notice>
    );
  }
  const error = reenvio.error;
  if (!error) return null;
  if (error instanceof ApiError && error.codigo === "correo_ya_verificado") {
    return <Notice tone="info">Tu correo ya está verificado.</Notice>;
  }
  return <Notice tone="danger">{error.message}</Notice>;
}

function ConfirmarEnlace({ token }: { token: string }) {
  const { data: usuario } = useSesion();
  const verificar = useVerificarCorreo();
  const reenvio = useReenviarVerificacion();

  // El enlace es de un solo uso: la guarda evita que el doble montaje de React en desarrollo
  // gaste el token con una primera petición y falle la segunda.
  const enviado = useRef(false);
  useEffect(() => {
    if (enviado.current) return;
    enviado.current = true;
    verificar.mutate(token);
  }, [token, verificar]);

  if (verificar.isSuccess) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <Encabezado
          titulo="Correo verificado"
          subtitulo="Tu correo quedó confirmado y el enlace ya no se puede volver a usar."
        />
        <Glass as="div" title="Listo">
          <p className="mb-4 flex items-start gap-2 text-success">
            <Icon name="check-circle" />
            <span className="text-ink">Ya puedes reservar, comprar y suscribirte a noticias.</span>
          </p>
          {usuario ? (
            <Button variant="primary" href={inicioDe(usuario)}>
              Ir a mi inicio
            </Button>
          ) : (
            <Button variant="primary" href="/login">
              Iniciar sesión
            </Button>
          )}
        </Glass>
      </div>
    );
  }

  if (verificar.isError) {
    const vencido =
      verificar.error instanceof ApiError && verificar.error.codigo === "enlace_invalido";
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <Encabezado
          titulo="No pudimos verificar tu correo"
          subtitulo="Hasta verificarlo no puedes reservar, comprar ni suscribirte a noticias."
        />
        <Glass as="div" title="Enlace vencido o ya usado">
          <Notice tone="danger">{vencido ? ENLACE_VENCIDO : verificar.error.message}</Notice>
          <ResultadoReenvio reenvio={reenvio} correo={usuario?.email ?? undefined} />
          {vencido && !reenvio.isSuccess && (
            <>
              {usuario ? (
                <Button
                  variant="primary"
                  onClick={() => reenvio.mutate()}
                  disabled={reenvio.isPending}
                >
                  {reenvio.isPending ? "Enviando…" : "Enviar un enlace nuevo"}
                </Button>
              ) : (
                <>
                  <p className="label sta-muted mb-3">Inicia sesión para pedir un enlace nuevo.</p>
                  <Button
                    variant="primary"
                    href={`/login?next=${encodeURIComponent(RUTA_VERIFICACION)}`}
                  >
                    Iniciar sesión
                  </Button>
                </>
              )}
            </>
          )}
        </Glass>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <Encabezado
        titulo="Verificando tu correo"
        subtitulo="Un momento, estamos confirmando el enlace."
      />
      <p role="status" className="label sta-muted">
        Verificando…
      </p>
    </div>
  );
}

function EstadoDeLaCuenta() {
  const { data: usuario, isPending } = useSesion();
  const aplica = usuario?.rol === "cliente" || usuario?.rol === "admin";
  const perfil = usePerfil(aplica);
  const reenvio = useReenviarVerificacion();

  if (isPending) return null;
  if (!usuario) {
    return <Navigate to={`/login?next=${encodeURIComponent(RUTA_VERIFICACION)}`} replace />;
  }
  if (!aplica) return <Navigate to={inicioDe(usuario)} replace />;
  if (perfil.isPending) return null;

  const encabezado = (
    <Encabezado
      titulo="Verifica tu correo"
      subtitulo="Hasta verificarlo no puedes reservar, comprar ni suscribirte a noticias."
    />
  );

  if (perfil.isError) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        {encabezado}
        <Notice tone="danger">{perfil.error.message}</Notice>
      </div>
    );
  }

  const { email, email_pendiente, email_verificado } = perfil.data;
  const pendiente = !email_verificado || Boolean(email_pendiente);
  const destino = email_pendiente ?? email;

  if (!pendiente) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        {encabezado}
        <Glass as="div" title="Tu correo ya está verificado">
          <p className="mb-4">
            <strong>{email}</strong> está confirmado. Ya puedes reservar, comprar y suscribirte a
            noticias.
          </p>
          <Button variant="primary" href={inicioDe(usuario)}>
            Ir a mi inicio
          </Button>
        </Glass>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      {encabezado}
      <Glass as="div" title="Te enviamos un enlace">
        <p className="mb-4">
          Lo enviamos a <strong>{destino}</strong>. Vence en 24 horas y solo funciona una vez.
        </p>
        <ResultadoReenvio reenvio={reenvio} correo={destino} />
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="primary" onClick={() => reenvio.mutate()} disabled={reenvio.isPending}>
            {reenvio.isPending ? "Enviando…" : "Reenviar enlace"}
          </Button>
          <Link className="sta-link" to="/perfil">
            Cambiar correo
          </Link>
        </div>
        <p className="caption sta-muted mt-4">
          Al reenviarlo, el enlace anterior deja de funcionar.
        </p>
      </Glass>
    </div>
  );
}
