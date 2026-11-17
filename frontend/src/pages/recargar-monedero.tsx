import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { z } from "zod";
import { ApiError, type Schemas } from "@/api/client";
import { useRecargar, useTarjetas } from "@/auth/monedero";
import { esRutaInterna } from "@/auth/roles";
import { Button } from "@/components/ui/button";
import { CampoDinero, CampoLista } from "@/components/ui/campos";
import { Form } from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Notice } from "@/components/ui/notice";
import { cop } from "@/lib/format";
import { NOMBRE_FRANQUICIA, NOMBRE_TIPO, soloDigitos } from "@/lib/tarjeta";

const MENSAJE_RED = "No pudimos comunicarnos con el servidor. Intenta de nuevo.";

const esquema = z.object({
  valor: z
    .string()
    .transform(soloDigitos)
    .pipe(
      z
        .string()
        .min(1, "Escribe el valor de la recarga.")
        .transform(Number)
        .pipe(z.number().min(1, "Debe ser mayor que 0.")),
    ),
  tarjeta_id: z.string().min(1, "Elige la tarjeta."),
});

type Entrada = z.input<typeof esquema>;
type Datos = z.output<typeof esquema>;

function Encabezado() {
  return (
    <div>
      <h1 className="sta-h1">Recargar monedero</h1>
      <p className="sta-sub">Recarga tu monedero desde una tarjeta registrada.</p>
    </div>
  );
}

/** HU-30: si viene de una compra o reserva con saldo insuficiente, dice cuánto falta y a dónde vuelve. */
function AvisoFaltante({
  faltante,
  codigo,
  volver,
}: {
  faltante: number;
  codigo: string | null;
  volver: string | null;
}) {
  const compra = volver?.startsWith("/compra/pago/") ?? false;
  const reserva = volver?.startsWith("/mis-viajes") ?? false;
  const de = compra ? "tu compra " : reserva ? "tu reserva " : "";
  const vuelta = compra
    ? " Al recargar volvemos al pago."
    : reserva
      ? " Al recargar volvemos a Mis viajes."
      : volver
        ? " Al recargar volvemos a donde estabas."
        : "";
  const texto = codigo
    ? `Vienes de ${de}${codigo}: te faltan ${cop(faltante)}.${vuelta}`
    : `Te faltan ${cop(faltante)} para continuar.${vuelta}`;
  return <Notice tone="info">{texto}</Notice>;
}

/** Formulario de recarga. Solo se pinta cuando ya se conocen las tarjetas registradas. */
function FormularioRecarga({
  tarjetas,
  faltante,
  codigo,
  volver,
  registrarHref,
}: {
  tarjetas: Schemas["Tarjeta"][];
  faltante: number | null;
  codigo: string | null;
  volver: string | null;
  registrarHref: string;
}) {
  const navigate = useNavigate();
  const recargar = useRecargar();
  const [movimiento, setMovimiento] = useState<Schemas["Movimiento"] | null>(null);
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null);

  const predeterminada = tarjetas.find((tarjeta) => !tarjeta.vencida) ?? tarjetas[0];
  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: {
      valor: faltante === null ? "" : cop(faltante),
      tarjeta_id: String(predeterminada.id),
    },
  });

  const valor = useWatch({ control: form.control, name: "valor" });
  const monto = Number(soloDigitos(String(valor ?? "")));

  const opciones = tarjetas.map((tarjeta) => ({
    value: String(tarjeta.id),
    label: `${NOMBRE_TIPO[tarjeta.tipo]}, ${NOMBRE_FRANQUICIA[tarjeta.franquicia]} ${
      tarjeta.numero_enmascarado
    }${tarjeta.vencida ? " · Vencida" : ""}`,
  }));

  const enviar = form.handleSubmit((datos) => {
    setErrorGeneral(null);
    form.clearErrors();
    recargar.mutate(
      { tarjeta_id: Number(datos.tarjeta_id), valor: datos.valor },
      {
        onSuccess: (movimiento) => {
          form.reset();
          if (volver) navigate(volver, { replace: true });
          else setMovimiento(movimiento);
        },
        // IU-07: el error del servidor se muestra junto al campo que lo causó.
        onError: (error) => {
          if (!(error instanceof ApiError)) {
            setErrorGeneral(MENSAJE_RED);
            return;
          }
          let mostrado = false;
          for (const [campo, mensaje] of Object.entries(error.campos)) {
            if (campo === "valor" || campo === "tarjeta_id") {
              form.setError(campo, { message: mensaje });
              mostrado = true;
            }
          }
          if (!mostrado) setErrorGeneral(error.message);
        },
      },
    );
  });

  if (movimiento) {
    return (
      <Glass as="div" title="Recarga aprobada">
        <p className="body">
          Recargaste {cop(movimiento.valor)} con la tarjeta {movimiento.referencia}.
        </p>
        <p className="label sta-muted mt-4">SALDO DISPONIBLE</p>
        <p className="sta-num title-lg">{cop(movimiento.saldo_resultante)}</p>
        <p className="caption sta-muted">
          Tu saldo aumentó exactamente en {cop(movimiento.valor)}.
        </p>
        <div className="mt-4">
          <Button variant="primary" href="/monedero">
            Ir al monedero
          </Button>
        </div>
      </Glass>
    );
  }

  return (
    <Glass as="div" title="Recargar">
      {faltante !== null && <AvisoFaltante faltante={faltante} codigo={codigo} volver={volver} />}
      <Form {...form}>
        <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
          {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

          <CampoDinero<Entrada> name="valor" label="Valor" />
          <CampoLista<Entrada> name="tarjeta_id" label="Desde la tarjeta" opciones={opciones} />

          <div className="mt-2 flex flex-col gap-2">
            <Button type="submit" variant="primary" disabled={recargar.isPending}>
              {recargar.isPending
                ? "Recargando…"
                : monto > 0
                  ? `Recargar ${cop(monto)}`
                  : "Recargar"}
            </Button>
            <p className="caption sta-muted">La recarga se aprueba si la tarjeta está vigente.</p>
          </div>

          <p className="caption sta-muted">
            ¿No ves tu tarjeta?{" "}
            <Link className="sta-link" to={registrarHref}>
              Registra una nueva
            </Link>
          </p>
        </form>
      </Form>
    </Glass>
  );
}

/** S23 · Recargar (HU-30). `?faltante=&codigo=&volver=` llegan desde una compra o una reserva. */
export function RecargarMonederoPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const tarjetas = useTarjetas();

  const valorFaltante = Number(params.get("faltante"));
  const faltante = Number.isInteger(valorFaltante) && valorFaltante > 0 ? valorFaltante : null;
  const codigo = params.get("codigo")?.trim() || null;
  const volverCrudo = params.get("volver");
  // Un `volver` inválido regresa al monedero; sin `volver` se queda con la confirmación.
  const volver =
    volverCrudo === null ? null : esRutaInterna(volverCrudo) ? volverCrudo : "/monedero";
  const registrarHref = `/monedero/tarjetas/nueva?volver=${encodeURIComponent(
    location.pathname + location.search,
  )}`;
  const tarjetasGuardadas = tarjetas.data ?? [];

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <Encabezado />

      {tarjetas.isPending ? (
        <Glass as="div" title="Recargar">
          <p className="body sta-muted">Cargando tarjetas…</p>
        </Glass>
      ) : tarjetas.isError ? (
        <Glass as="div" title="Recargar">
          <Notice tone="danger">No pudimos cargar tus tarjetas. Intenta de nuevo.</Notice>
          <div className="mt-4">
            <Button
              variant="secondary"
              onClick={() => tarjetas.refetch()}
              disabled={tarjetas.isFetching}
            >
              Reintentar
            </Button>
          </div>
        </Glass>
      ) : tarjetasGuardadas.length === 0 ? (
        <Glass as="div" title="Recargar">
          {faltante !== null && (
            <AvisoFaltante faltante={faltante} codigo={codigo} volver={volver} />
          )}
          <p className="body">
            No tienes tarjetas registradas. Registra una para recargar tu monedero.
          </p>
          <div className="mt-4">
            <Button variant="primary" href={registrarHref}>
              Registrar tarjeta
            </Button>
          </div>
        </Glass>
      ) : (
        <FormularioRecarga
          tarjetas={tarjetasGuardadas}
          faltante={faltante}
          codigo={codigo}
          volver={volver}
          registrarHref={registrarHref}
        />
      )}
    </div>
  );
}
