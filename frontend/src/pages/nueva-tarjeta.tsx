import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { CLAVE_MONEDERO, registrarTarjeta } from "@/auth/monedero";
import { esRutaInterna } from "@/auth/roles";
import { Button } from "@/components/ui/button";
import { CampoLista, CampoTexto } from "@/components/ui/campos";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import { agruparNumero, pasaLuhn, soloDigitos, tarjetaVencida } from "@/lib/tarjeta";

const MENSAJE_RED = "No pudimos comunicarnos con el servidor. Intenta de nuevo.";

const TIPOS = [
  { value: "credito", label: "Crédito" },
  { value: "debito", label: "Débito" },
];

const CAMPOS_API = ["numero", "vencimiento", "cvv", "titular"] as const;
type CampoApi = (typeof CAMPOS_API)[number];
const esCampoApi = (campo: string): campo is CampoApi =>
  (CAMPOS_API as readonly string[]).includes(campo);

const esquema = z.object({
  tipo: z.enum(["credito", "debito"]),
  numero: z
    .string()
    .transform(soloDigitos)
    .pipe(
      z
        .string()
        .min(13, "Escribe un número de 13 a 19 dígitos.")
        .max(19, "Escribe un número de 13 a 19 dígitos.")
        .refine(pasaLuhn, "El número no es válido. Revisa los dígitos."),
    ),
  titular: z
    .string()
    .trim()
    .min(1, "Escribe el nombre del titular.")
    .max(100, "Máximo 100 caracteres.")
    .regex(/^[\p{L}][\p{L} '.-]*$/u, "Usa solo letras, espacios, apóstrofo o guion."),
  vencimiento: z
    .string()
    .regex(/^(0[1-9]|1[0-2])\/\d{2}$/, "Escribe el vencimiento como MM/AA.")
    .refine((valor) => !tarjetaVencida(valor), "La tarjeta está vencida."),
  cvv: z.string().regex(/^\d{3,4}$/, "El CVV debe tener 3 o 4 dígitos."),
});

type Entrada = z.input<typeof esquema>;
type Datos = z.output<typeof esquema>;

/** S23 · Registrar tarjeta (HU-28). `?volver=<ruta>` regresa a la recarga o a la compra. */
export function NuevaTarjetaPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [enviando, setEnviando] = useState(false);
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null);

  const form = useForm<Entrada, unknown, Datos>({
    resolver: zodResolver(esquema),
    defaultValues: { tipo: "credito", numero: "", titular: "", vencimiento: "", cvv: "" },
  });

  const enviar = form.handleSubmit(async (datos) => {
    setErrorGeneral(null);
    form.clearErrors();
    setEnviando(true);
    try {
      await registrarTarjeta(datos);
      await queryClient.invalidateQueries({ queryKey: CLAVE_MONEDERO });
      form.reset();
      const volver = params.get("volver");
      navigate(esRutaInterna(volver) ? volver : "/monedero", { replace: true });
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setErrorGeneral(MENSAJE_RED);
        return;
      }
      let mostrado = false;
      // IU-07: el error del servidor se muestra junto al campo que lo causó.
      for (const [campo, mensaje] of Object.entries(error.campos)) {
        if (esCampoApi(campo)) {
          form.setError(campo, { message: mensaje });
          mostrado = true;
        }
      }
      if (!mostrado) setErrorGeneral(error.message);
    } finally {
      setEnviando(false);
    }
  });

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <div>
        <h1 className="sta-h1">Registrar tarjeta</h1>
        <p className="sta-sub">
          Tarjetas simuladas: guardamos solo los últimos 4 dígitos. El CVV no se almacena.
        </p>
      </div>

      <Glass as="div" title="Datos de la tarjeta">
        <Form {...form}>
          <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
            {errorGeneral && <Notice tone="danger">{errorGeneral}</Notice>}

            <CampoLista<Entrada> name="tipo" label="Tipo" opciones={TIPOS} />

            <FormField
              control={form.control}
              name="numero"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Número</FormLabel>
                  <FormControl>
                    <Input
                      inputMode="numeric"
                      autoComplete="off"
                      placeholder="4242 4242 4242 4242"
                      maxLength={23}
                      {...field}
                      value={agruparNumero(String(field.value ?? ""))}
                      onChange={(evento) =>
                        field.onChange(soloDigitos(evento.target.value).slice(0, 19))
                      }
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <CampoTexto<Entrada>
              name="titular"
              label="Nombre del titular"
              placeholder="LAURA GOMEZ RIOS"
              autoComplete="off"
              maxLength={100}
            />

            <div className="grid grid-cols-2 gap-3">
              <CampoTexto<Entrada>
                name="vencimiento"
                label="Vence"
                placeholder="MM/AA"
                inputMode="numeric"
                autoComplete="off"
                maxLength={5}
              />
              <CampoTexto<Entrada>
                name="cvv"
                label="CVV"
                type="password"
                placeholder="123"
                inputMode="numeric"
                autoComplete="off"
                maxLength={4}
                ayuda="Solo lo validamos, no lo guardamos."
              />
            </div>

            <div className="mt-2">
              <Button type="submit" variant="primary" disabled={enviando}>
                {enviando ? "Registrando…" : "Registrar tarjeta"}
              </Button>
            </div>
          </form>
        </Form>
      </Glass>
    </div>
  );
}
