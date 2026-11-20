import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { api, ApiError, unwrap } from "@/api/client";
import { PERFIL_KEY } from "./perfil";
import { esRutaInterna } from "./roles";
import { SESION_KEY } from "./sesion";

/** Ruta del frontend a la que lleva el enlace del correo (`?token=…`). */
export const RUTA_VERIFICACION = "/verificar-correo";

/** HU-02: la API responde 403 `correo_no_verificado` al reservar, comprar o pagar. */
export const esCorreoNoVerificado = (error: unknown): boolean =>
  error instanceof ApiError && error.codigo === "correo_no_verificado";

/** La verificación con `?volver=` para regresar a donde estaba el cliente. */
export const rutaVerificacion = (volver: string) =>
  `${RUTA_VERIFICACION}?volver=${encodeURIComponent(volver)}`;

const CLAVE_REGRESO = "sta-regreso-verificacion";
/** Lo que vale el enlace del correo. */
const VIGENCIA_REGRESO_MS = 24 * 60 * 60 * 1000;

/** Copia del destino para la pestaña que abre el enlace del correo, que llega sin `?volver=`.
 *  Solo guarda una ruta interna, nunca datos de los viajeros. */
export function recordarRegreso(ruta: string) {
  if (!esRutaInterna(ruta)) return;
  try {
    localStorage.setItem(
      CLAVE_REGRESO,
      JSON.stringify({ ruta, hasta: Date.now() + VIGENCIA_REGRESO_MS }),
    );
  } catch {
    /* sin almacenamiento solo se pierde el atajo de la otra pestaña */
  }
}

/** El destino guardado, si es interno y no venció. Se borra al leerlo: sirve una sola vez. */
export function tomarRegreso(): string | null {
  try {
    const guardado = localStorage.getItem(CLAVE_REGRESO);
    localStorage.removeItem(CLAVE_REGRESO);
    if (!guardado) return null;
    const { ruta, hasta } = JSON.parse(guardado) as { ruta?: unknown; hasta?: unknown };
    return typeof ruta === "string" &&
      esRutaInterna(ruta) &&
      typeof hasta === "number" &&
      hasta > Date.now()
      ? ruta
      : null;
  } catch {
    return null;
  }
}

/** HU-02: lleva a la verificación a quien intentó reservar o comprar sin el correo verificado. */
export function useIrAVerificacion() {
  const navigate = useNavigate();
  return (volver: string) => {
    recordarRegreso(volver);
    void navigate(rutaVerificacion(volver));
  };
}

/** Confirma el enlace del correo (HU-02). No exige sesión: el enlace puede abrirse en otro
 *  dispositivo. Si hay sesión, se vuelve a pedir el usuario para que `email_verificado` cambie. */
export function useVerificarCorreo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      unwrap(api.POST("/api/v1/usuarios/verificacion", { body: { token } })),
    onSuccess: async () => {
      // Si la sesión aún se estaba cargando cuando se confirmó el enlace, esa respuesta puede traer
      // el correo sin verificar: se descarta para que la consulta nueva salga después de verificar.
      await queryClient.cancelQueries({ queryKey: SESION_KEY });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: SESION_KEY }),
        queryClient.invalidateQueries({ queryKey: PERFIL_KEY }),
      ]);
    },
  });
}

/** Pide un enlace nuevo; el anterior deja de servir. */
export function useReenviarVerificacion() {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/usuarios/me/verificacion/reenviar")),
  });
}
