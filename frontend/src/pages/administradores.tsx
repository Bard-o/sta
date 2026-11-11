import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError, type Schemas } from "@/api/client";
import {
  useAdministradores,
  useCrearAdministrador,
  useDesactivarAdministrador,
  useReactivarAdministrador,
  useReenviarInvitacion,
} from "@/auth/administradores";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogNotice,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Glass } from "@/components/ui/glass";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fecha, fechaHora, ZONA_COLOMBIA } from "@/lib/format";

type Administrador = Schemas["AdministradorSalida"];

const ESTADOS: Record<Administrador["estado"], { tono: Tone; texto: string }> = {
  activo: { tono: "success", texto: "Activo" },
  inactivo: { tono: "neutral", texto: "Inactivo" },
  invitacion_pendiente: { tono: "info", texto: "Invitación pendiente" },
  invitacion_vencida: { tono: "neutral", texto: "Invitación vencida" },
};

/** Estado visible; la invitación pendiente muestra su vencimiento (HU-10). */
function textoEstado(admin: Administrador): string {
  const estado = ESTADOS[admin.estado];
  if (admin.estado === "invitacion_pendiente" && admin.invitacion_expira_en) {
    return `${estado.texto} · vence ${fechaHora(admin.invitacion_expira_en, ZONA_COLOMBIA)}`;
  }
  return estado.texto;
}

/** Nombre para mostrar. El administrador sin registro no tiene nombres todavía (HU-10). */
function nombreCompleto(admin: Administrador): string {
  return [admin.nombres, admin.apellidos].filter(Boolean).join(" ") || "Sin completar";
}

const esquema = z.object({
  nombre_usuario: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9._-]{3,50}$/, "Usa de 3 a 50 letras, números, punto, guion o guion bajo."),
  email: z
    .string()
    .trim()
    .regex(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, "Escribe un correo válido."),
});

type Datos = z.infer<typeof esquema>;

/** S06 · Gestión de administradores (HU-10, HU-11, HU-12). Solo el root llega aquí: la ruta y
 *  el menú están restringidos a su rol y el servidor vuelve a validar cada petición (RF-02,
 *  RNF-10). */
export function AdministradoresPage() {
  const administradores = useAdministradores();
  const crear = useCrearAdministrador();
  const desactivar = useDesactivarAdministrador();
  const reactivar = useReactivarAdministrador();
  const reenviar = useReenviarInvitacion();

  const [paraDesactivar, setParaDesactivar] = useState<Administrador | null>(null);
  const [paraReenviar, setParaReenviar] = useState<Administrador | null>(null);
  const [emailReenvio, setEmailReenvio] = useState("");
  const [errorReenvio, setErrorReenvio] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const form = useForm<Datos>({
    resolver: zodResolver(esquema),
    defaultValues: { nombre_usuario: "", email: "" },
  });

  // Solo se bloquea la fila que está en curso, no todas.
  const enCurso = desactivar.isPending
    ? desactivar.variables
    : reactivar.isPending
      ? reactivar.variables
      : reenviar.isPending
        ? reenviar.variables.adminId
        : undefined;

  const enviar = form.handleSubmit((datos) => {
    setAviso(null);
    crear.mutate(datos, {
      onSuccess: (admin) => {
        form.reset();
        setAviso(
          `Invitamos a ${admin.nombre_usuario}. Le enviamos el enlace a ${admin.email} y vence en 72 horas.`,
        );
      },
      // IU-07: el error de cada campo se muestra junto a ese campo.
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        for (const [campo, mensaje] of Object.entries(error.campos)) {
          if (campo === "nombre_usuario" || campo === "email") {
            form.setError(campo, { message: mensaje });
          }
        }
      },
    });
  });

  const confirmarDesactivacion = () => {
    if (!paraDesactivar) return;
    const admin = paraDesactivar;
    setErrorAccion(null);
    setAviso(null);
    desactivar.mutate(admin.id, {
      onSuccess: () => {
        setParaDesactivar(null);
        setAviso(`Desactivamos a ${admin.nombre_usuario}. Ya no puede iniciar sesión.`);
      },
      onError: (error) => {
        setParaDesactivar(null);
        setErrorAccion(error.message);
      },
    });
  };

  const reactivarAdministrador = (admin: Administrador) => {
    setErrorAccion(null);
    setAviso(null);
    reactivar.mutate(admin.id, {
      onSuccess: () => {
        if (!admin.nombres && !admin.apellidos) {
          setAviso(
            `Reactivamos a ${admin.nombre_usuario}. Reenvíale la invitación para que pueda entrar.`,
          );
        } else {
          setAviso(`Reactivamos a ${admin.nombre_usuario}. Puede volver a iniciar sesión.`);
        }
      },
      onError: (error) => setErrorAccion(error.message),
    });
  };

  const enviarInvitacion = (admin: Administrador, email?: string) => {
    setErrorAccion(null);
    setAviso(null);
    reenviar.mutate(
      { adminId: admin.id, email },
      {
        onSuccess: (actualizado) => {
          setParaReenviar(null);
          setEmailReenvio("");
          setErrorReenvio(null);
          setAviso(
            `Reenviamos la invitación a ${actualizado.email}. El enlace anterior dejó de servir.`,
          );
        },
        onError: (error) => {
          if (paraReenviar) {
            setErrorReenvio(error.message);
          } else {
            setErrorAccion(error.message);
          }
        },
      },
    );
  };

  const reenviarAdministrador = (admin: Administrador) => {
    if (admin.email) {
      enviarInvitacion(admin);
      return;
    }
    setEmailReenvio("");
    setErrorReenvio(null);
    setParaReenviar(admin);
  };

  const camposCrear = crear.error instanceof ApiError ? crear.error.campos : {};
  const errorCrearGeneral =
    crear.error && !camposCrear.nombre_usuario && !camposCrear.email
      ? crear.error.message
      : null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="sta-h1">Administradores</h1>
        <p className="sta-sub">
          Solo el root invita administradores. La contraseña la define cada uno al abrir el enlace
          que recibe por correo; desactivar conserva su historial en la auditoría.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Glass aria-label="Administradores" className="min-w-0 xl:col-span-3">
          {aviso && <Notice tone="info">{aviso}</Notice>}
          {errorAccion && <Notice tone="danger">{errorAccion}</Notice>}

          {administradores.isError ? (
            <Notice tone="danger">
              No pudimos cargar los administradores.{" "}
              <Button size="sm" variant="ghost" onClick={() => void administradores.refetch()}>
                Reintentar
              </Button>
            </Notice>
          ) : administradores.isPending ? (
            <p className="body sta-muted">Cargando administradores…</p>
          ) : administradores.data.length === 0 ? (
            <p className="body sta-muted">Todavía no hay administradores.</p>
          ) : (
            <Table aria-label="Administradores">
              <TableHeader>
                <TableRow>
                  <TableHead>Usuario</TableHead>
                  <TableHead>Correo</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Creado</TableHead>
                  <TableHead>
                    <span className="sr-only">Acciones</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {administradores.data.map((admin) => {
                  const estado = ESTADOS[admin.estado];
                  const sinCompletar =
                    admin.estado === "invitacion_pendiente" ||
                    admin.estado === "invitacion_vencida";
                  return (
                    <TableRow key={admin.id}>
                      <TableCell className="body-strong">{admin.nombre_usuario}</TableCell>
                      <TableCell>
                        {admin.email || <span className="sta-muted">Sin correo</span>}
                      </TableCell>
                      <TableCell>
                        {admin.nombres || admin.apellidos ? (
                          nombreCompleto(admin)
                        ) : (
                          <span className="sta-muted">Sin completar</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge tone={estado.tono}>{textoEstado(admin)}</Badge>
                      </TableCell>
                      <TableCell>{fecha(admin.creado_en, ZONA_COLOMBIA)}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          {sinCompletar && (
                            <Button
                              size="sm"
                              variant="secondary"
                              aria-label={`Reenviar invitación a ${admin.nombre_usuario}`}
                              disabled={enCurso === admin.id}
                              onClick={() => reenviarAdministrador(admin)}
                            >
                              Reenviar invitación
                            </Button>
                          )}
                          {admin.estado === "inactivo" ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              aria-label={`Reactivar a ${admin.nombre_usuario}`}
                              disabled={enCurso === admin.id}
                              onClick={() => reactivarAdministrador(admin)}
                            >
                              Reactivar
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={`Desactivar a ${admin.nombre_usuario}`}
                              disabled={enCurso === admin.id}
                              onClick={() => setParaDesactivar(admin)}
                            >
                              Desactivar
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </Glass>

        <Glass as="div" title="Invitar administrador" className="min-w-0 xl:col-span-2">
          <Form {...form}>
            <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
              {errorCrearGeneral && <Notice tone="danger">{errorCrearGeneral}</Notice>}

              <FormField
                control={form.control}
                name="nombre_usuario"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombre de usuario</FormLabel>
                    <FormControl>
                      <Input autoComplete="off" autoFocus {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Correo</FormLabel>
                    <FormControl>
                      <Input type="email" autoComplete="email" {...field} />
                    </FormControl>
                    <FormDescription>
                      Le enviaremos un enlace de un solo uso, válido por 72 horas.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="mt-1">
                <Button type="submit" variant="primary" disabled={crear.isPending}>
                  {crear.isPending ? "Enviando…" : "Enviar invitación"}
                </Button>
              </div>
            </form>
          </Form>
        </Glass>
      </div>

      <Dialog
        open={paraDesactivar !== null}
        onOpenChange={(abierto) => {
          if (!abierto) setParaDesactivar(null);
        }}
      >
        <DialogContent>
          <DialogTitle>¿Desactivar al administrador {paraDesactivar?.nombre_usuario}?</DialogTitle>
          <DialogDescription>
            {paraDesactivar
              ? `${nombreCompleto(paraDesactivar)} · ${ESTADOS[paraDesactivar.estado].texto}`
              : null}
          </DialogDescription>
          <DialogBody>
            <DialogNotice tone="danger">
              No podrá iniciar sesión y se cerrarán sus sesiones. Si tiene una invitación pendiente,
              el enlace dejará de servir. Sus acciones pasadas se conservan en la auditoría.
            </DialogNotice>
          </DialogBody>
          <DialogFooter>
            <Button
              variant="danger"
              onClick={confirmarDesactivacion}
              disabled={desactivar.isPending}
            >
              {desactivar.isPending ? "Desactivando…" : "Desactivar administrador"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => setParaDesactivar(null)}
              disabled={desactivar.isPending}
            >
              Volver
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={paraReenviar !== null}
        onOpenChange={(abierto) => {
          if (!abierto) setParaReenviar(null);
        }}
      >
        <DialogContent>
          <DialogTitle>Correo para reenviar la invitación</DialogTitle>
          <DialogDescription>
            La cuenta {paraReenviar?.nombre_usuario} no tiene un correo guardado. Escríbelo para
            enviarle un enlace nuevo.
          </DialogDescription>
          <DialogBody>
            <div className="sta-field">
              <label htmlFor="email-reenvio" className="sta-field__label">
                Correo
              </label>
              <Input
                id="email-reenvio"
                type="email"
                autoComplete="email"
                value={emailReenvio}
                onChange={(evento) => setEmailReenvio(evento.target.value)}
              />
            </div>
            {errorReenvio && <DialogNotice tone="danger">{errorReenvio}</DialogNotice>}
          </DialogBody>
          <DialogFooter>
            <Button
              variant="primary"
              onClick={() => {
                if (!paraReenviar) return;
                enviarInvitacion(paraReenviar, emailReenvio.trim());
              }}
              disabled={reenviar.isPending || emailReenvio.trim() === ""}
            >
              {reenviar.isPending ? "Enviando…" : "Enviar invitación"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => setParaReenviar(null)}
              disabled={reenviar.isPending}
            >
              Volver
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
