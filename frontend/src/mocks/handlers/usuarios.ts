// Módulo usuarios (HU-01 a HU-12). Valores que disparan errores: ver comentarios de cada handler.
import type { Schemas } from "@/api/client";
import { BLOQUEOS_DESACTIVACION, CONTRASENA_MOCK, usuarioDe } from "../datos";
import { db, error, exigirRol, nuevoId, sesion } from "../estado";
import { http } from "../http";

const POLITICA = /^(?=.*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])(?=.*\d).{8,}$/;
const MENSAJE_POLITICA = "Debe tener al menos 8 caracteres, con letras y números.";
const enlaceInvalido = () =>
  error(400, "enlace_invalido", "Este enlace venció o ya fue usado. Pide uno nuevo.");

type Perfil = Schemas["PerfilSalida"];

function cuentaDeSesion() {
  const usuario = sesion.get();
  return db.cuentas.find((c) => c.usuario.id === usuario?.id);
}

function camposContrasenaNueva(
  nueva: string,
  confirmacion: string,
): Record<string, string> | undefined {
  if (!POLITICA.test(nueva)) return { contrasena_nueva: MENSAJE_POLITICA };
  if (nueva !== confirmacion) return { confirmacion: "No coincide con la contraseña nueva." };
  return undefined;
}

function perfilNuevo(
  id: number,
  nombre_usuario: string,
  rol: Perfil["rol"],
  datos: Schemas["RegistroClienteEntrada"] | Schemas["RegistroAdministradorEntrada"],
): Perfil {
  return {
    id,
    nombre_usuario,
    rol,
    tipo_documento: datos.tipo_documento,
    numero_documento: datos.numero_documento,
    nombres: datos.nombres,
    apellidos: datos.apellidos,
    fecha_nacimiento: datos.fecha_nacimiento,
    lugar_nacimiento: datos.lugar_nacimiento,
    direccion_facturacion: datos.direccion_facturacion,
    genero: datos.genero,
    email: datos.email.toLowerCase(),
    email_verificado: false,
    email_pendiente: null,
    telefono: datos.telefono ?? null,
    imagen_url: null,
    suscrito_noticias: false,
  };
}

export const usuariosHandlers = [
  // ---------- Sesión (HU-03, HU-04) ----------

  http.post("/api/v1/auth/login", async ({ request, response }) => {
    const { usuario, contrasena } = await request.json();
    const clave = usuario.trim().toLowerCase();
    if (clave === "bloqueado") {
      return response.untyped(
        error(
          429,
          "demasiados_intentos",
          "Cuenta bloqueada. Intenta de nuevo en 15 minutos.",
          undefined,
          {
            "Retry-After": "900",
          },
        ),
      );
    }
    const cuenta = db.cuentas.find(
      (c) => c.usuario.nombre_usuario === clave || c.usuario.email === clave,
    );
    if (!cuenta || contrasena !== CONTRASENA_MOCK) {
      return response.untyped(
        error(401, "credenciales_invalidas", "Usuario o contraseña incorrectos."),
      );
    }
    if (!cuenta.activo) return response.untyped(error(403, "cuenta_inactiva", "Cuenta inactiva."));
    sesion.set(cuenta.usuario);
    return response(200).json(cuenta.usuario);
  }),

  http.post("/api/v1/auth/logout", ({ response }) => {
    sesion.set(null);
    return response(204).empty();
  }),

  http.get("/api/v1/auth/me", ({ response }) => {
    const usuario = sesion.get();
    if (!usuario)
      return response.untyped(error(401, "no_autenticado", "Inicia sesión para continuar."));
    return response(200).json(usuario);
  }),

  // ---------- Restablecer contraseña (HU-05). Token «vencido» → enlace_invalido ----------

  http.post("/api/v1/auth/restablecimiento", ({ response }) =>
    response(202).json({
      mensaje: "Si el correo está registrado, recibirás un enlace válido por 30 minutos.",
    }),
  ),

  http.post("/api/v1/auth/restablecimiento/confirmar", async ({ request, response }) => {
    const datos = await request.json();
    if (datos.token === "vencido") return response.untyped(enlaceInvalido());
    const campos = camposContrasenaNueva(datos.contrasena_nueva, datos.confirmacion);
    if (campos) {
      return response.untyped(error(422, "datos_invalidos", "Revisa los campos marcados.", campos));
    }
    return response(204).empty();
  }),

  // ---------- Registro y verificación (HU-01, HU-02) ----------

  // nombre_usuario, documento o correo de una cuenta existente → datos_duplicados.
  http.post("/api/v1/usuarios/registro", async ({ request, response }) => {
    const datos = await request.json();
    const campos: Record<string, string> = {};
    if (!datos.acepta_politica) campos.acepta_politica = "Debes aceptar la política de datos.";
    if (datos.fecha_nacimiento > new Date().toISOString().slice(0, 10)) {
      campos.fecha_nacimiento = "La fecha de nacimiento no puede ser futura.";
    }
    if (!POLITICA.test(datos.contrasena)) campos.contrasena = MENSAJE_POLITICA;
    if (Object.keys(campos).length) {
      return response.untyped(error(422, "datos_invalidos", "Revisa los campos marcados.", campos));
    }
    const clientes = db.cuentas.filter((c) => c.usuario.rol === "cliente");
    const duplicados: Record<string, string> = {};
    if (db.cuentas.some((c) => c.usuario.nombre_usuario === datos.nombre_usuario.toLowerCase())) {
      duplicados.nombre_usuario = "Ese nombre de usuario ya está en uso.";
    }
    if (clientes.some((c) => c.perfil?.numero_documento === datos.numero_documento)) {
      duplicados.numero_documento = "Ya existe una cuenta con este documento.";
    }
    if (clientes.some((c) => c.usuario.email === datos.email.toLowerCase())) {
      duplicados.email = "Ya existe una cuenta con este correo.";
    }
    if (Object.keys(duplicados).length) {
      return response.untyped(
        error(409, "datos_duplicados", "Ya existe una cuenta con estos datos.", duplicados),
      );
    }
    const perfil = perfilNuevo(nuevoId(), datos.nombre_usuario.toLowerCase(), "cliente", datos);
    const usuario = usuarioDe(perfil);
    db.cuentas.push({ usuario, perfil, activo: true });
    sesion.set(usuario);
    return response(201).json(usuario);
  }),

  // Token «vencido» → enlace_invalido. Cualquier otro verifica el correo de la sesión.
  http.post("/api/v1/usuarios/verificacion", async ({ request, response }) => {
    const { token } = await request.json();
    if (token === "vencido") return response.untyped(enlaceInvalido());
    const cuenta = cuentaDeSesion();
    if (cuenta?.perfil) {
      cuenta.perfil.email = cuenta.perfil.email_pendiente ?? cuenta.perfil.email;
      cuenta.perfil.email_pendiente = null;
      cuenta.perfil.email_verificado = true;
      cuenta.usuario = { ...cuenta.usuario, email: cuenta.perfil.email, email_verificado: true };
      sesion.set(cuenta.usuario);
    }
    return response(204).empty();
  }),

  http.post("/api/v1/usuarios/me/verificacion/reenviar", ({ response }) => {
    const bloqueo = exigirRol(["cliente", "admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const perfil = cuentaDeSesion()?.perfil;
    if (perfil?.email_verificado && !perfil.email_pendiente) {
      return response.untyped(error(409, "correo_ya_verificado", "Tu correo ya está verificado."));
    }
    return response(204).empty();
  }),

  // ---------- Contraseña y perfil (HU-06, HU-07) ----------

  http.put("/api/v1/usuarios/me/contrasena", async ({ request, response }) => {
    const bloqueo = exigirRol(["cliente", "admin", "root"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    if (datos.contrasena_actual !== CONTRASENA_MOCK) {
      return response.untyped(
        error(422, "contrasena_actual_incorrecta", "La contraseña actual no es correcta.", {
          contrasena_actual: "La contraseña actual no es correcta.",
        }),
      );
    }
    const campos = camposContrasenaNueva(datos.contrasena_nueva, datos.confirmacion);
    if (campos) {
      return response.untyped(error(422, "datos_invalidos", "Revisa los campos marcados.", campos));
    }
    return response(204).empty();
  }),

  http.get("/api/v1/usuarios/me/perfil", ({ response }) => {
    const bloqueo = exigirRol(["cliente", "admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const perfil = cuentaDeSesion()?.perfil;
    if (!perfil) return response.untyped(error(404, "no_encontrado", "El recurso no existe."));
    return response(200).json(perfil);
  }),

  // Un correo distinto queda en email_pendiente hasta verificarlo (HU-07).
  http.put("/api/v1/usuarios/me/perfil", async ({ request, response }) => {
    const bloqueo = exigirRol(["cliente", "admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const cuenta = cuentaDeSesion();
    if (!cuenta?.perfil)
      return response.untyped(error(404, "no_encontrado", "El recurso no existe."));
    const email = datos.email.toLowerCase();
    const cambiaCorreo = email !== cuenta.perfil.email;
    const enUso = db.cuentas.some(
      (c) => c !== cuenta && c.usuario.rol === cuenta.usuario.rol && c.usuario.email === email,
    );
    if (cambiaCorreo && enUso) {
      return response.untyped(
        error(409, "datos_duplicados", "Ya existe una cuenta con estos datos.", {
          email: "Ya existe una cuenta con este correo.",
        }),
      );
    }
    cuenta.perfil = {
      ...cuenta.perfil,
      ...datos,
      email: cuenta.perfil.email,
      telefono: datos.telefono ?? null,
      email_pendiente: cambiaCorreo ? email : cuenta.perfil.email_pendiente,
    };
    cuenta.usuario = { ...cuenta.usuario, nombres: datos.nombres, apellidos: datos.apellidos };
    sesion.set(cuenta.usuario);
    return response(200).json(cuenta.perfil);
  }),

  http.put("/api/v1/usuarios/me/imagen", ({ response }) => {
    const bloqueo = exigirRol(["cliente", "admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const cuenta = cuentaDeSesion()!;
    cuenta.perfil = { ...cuenta.perfil!, imagen_url: `/api/v1/usuarios/me/imagen?v=${Date.now()}` };
    return response(200).json(cuenta.perfil);
  }),

  http.delete("/api/v1/usuarios/me/imagen", ({ response }) => {
    const bloqueo = exigirRol(["cliente", "admin"]);
    if (bloqueo) return response.untyped(bloqueo);
    const cuenta = cuentaDeSesion()!;
    cuenta.perfil = { ...cuenta.perfil!, imagen_url: null };
    return response(204).empty();
  }),

  // ---------- Noticias y desactivación (HU-08, HU-09) ----------

  http.put("/api/v1/usuarios/me/suscripcion", async ({ request, response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const { noticias } = await request.json();
    const cuenta = cuentaDeSesion()!;
    if (noticias && !cuenta.perfil?.email_verificado) {
      return response.untyped(
        error(403, "correo_no_verificado", "Verifica tu correo para suscribirte a noticias."),
      );
    }
    cuenta.perfil = { ...cuenta.perfil!, suscrito_noticias: noticias };
    return response(200).json({ noticias });
  }),

  http.post("/api/v1/usuarios/suscripcion/baja", async ({ request, response }) => {
    const { token } = await request.json();
    if (token === "vencido") return response.untyped(enlaceInvalido());
    return response(204).empty();
  }),

  http.get("/api/v1/usuarios/me/desactivacion", ({ response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    const bloqueos = BLOQUEOS_DESACTIVACION[sesion.get()!.nombre_usuario] ?? [];
    return response(200).json({ puede_desactivar: bloqueos.length === 0, bloqueos });
  }),

  // lauragomez tiene una compra activa → tiquetes_activos.
  http.post("/api/v1/usuarios/me/desactivacion", ({ response }) => {
    const bloqueo = exigirRol(["cliente"]);
    if (bloqueo) return response.untyped(bloqueo);
    if (BLOQUEOS_DESACTIVACION[sesion.get()!.nombre_usuario]?.length) {
      return response.untyped(
        error(409, "tiquetes_activos", "Tienes compras o reservas activas en vuelos futuros."),
      );
    }
    cuentaDeSesion()!.activo = false;
    sesion.set(null);
    return response(204).empty();
  }),

  // ---------- Administradores (HU-10, HU-11, HU-12) ----------

  http.get("/api/v1/administradores", ({ response }) => {
    const bloqueo = exigirRol(["root"]);
    if (bloqueo) return response.untyped(bloqueo);
    return response(200).json(db.administradores);
  }),

  http.post("/api/v1/administradores", async ({ request, response }) => {
    const bloqueo = exigirRol(["root"]);
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const nombre = datos.nombre_usuario.toLowerCase();
    const existe =
      db.cuentas.some((c) => c.usuario.nombre_usuario === nombre) ||
      db.administradores.some((a) => a.nombre_usuario === nombre);
    if (existe) {
      return response.untyped(
        error(409, "datos_duplicados", "Ya existe una cuenta con estos datos.", {
          nombre_usuario: "Ese nombre de usuario ya existe.",
        }),
      );
    }
    if (!POLITICA.test(datos.contrasena_temporal)) {
      return response.untyped(
        error(422, "datos_invalidos", "Revisa los campos marcados.", {
          contrasena_temporal: MENSAJE_POLITICA,
        }),
      );
    }
    const admin = {
      id: nuevoId(),
      nombre_usuario: nombre,
      nombres: null,
      apellidos: null,
      estado: "registro_incompleto" as const,
      creado_en: new Date().toISOString(),
    };
    db.administradores.unshift(admin);
    return response(201).json(admin);
  }),

  http.post("/api/v1/administradores/{admin_id}/desactivar", ({ params, response }) => {
    const bloqueo = exigirRol(["root"]);
    if (bloqueo) return response.untyped(bloqueo);
    const admin = db.administradores.find((a) => a.id === Number(params.admin_id));
    if (!admin) return response.untyped(error(404, "no_encontrado", "El administrador no existe."));
    if (admin.estado === "inactivo") {
      return response.untyped(error(409, "estado_invalido", "El administrador ya está inactivo."));
    }
    admin.estado = "inactivo";
    return response(200).json(admin);
  }),

  http.post("/api/v1/administradores/{admin_id}/reactivar", ({ params, response }) => {
    const bloqueo = exigirRol(["root"]);
    if (bloqueo) return response.untyped(bloqueo);
    const admin = db.administradores.find((a) => a.id === Number(params.admin_id));
    if (!admin) return response.untyped(error(404, "no_encontrado", "El administrador no existe."));
    if (admin.estado !== "inactivo") {
      return response.untyped(error(409, "estado_invalido", "El administrador ya está activo."));
    }
    admin.estado = admin.nombres ? "activo" : "registro_incompleto";
    return response(200).json(admin);
  }),

  http.post("/api/v1/administradores/me/registro", async ({ request, response }) => {
    const bloqueo = exigirRol(["admin"], { registroIncompleto: true });
    if (bloqueo) return response.untyped(bloqueo);
    const datos = await request.json();
    const usuario = sesion.get()!;
    if (usuario.registro_completo) {
      return response.untyped(error(409, "registro_ya_completo", "Tu registro ya está completo."));
    }
    if (datos.contrasena_temporal !== CONTRASENA_MOCK) {
      return response.untyped(
        error(422, "contrasena_actual_incorrecta", "La contraseña temporal no es correcta.", {
          contrasena_temporal: "La contraseña temporal no es correcta.",
        }),
      );
    }
    const campos = camposContrasenaNueva(datos.contrasena_nueva, datos.confirmacion);
    if (campos) {
      return response.untyped(error(422, "datos_invalidos", "Revisa los campos marcados.", campos));
    }
    // El correo del administrador no pasa por verificación en la iteración 1.
    const perfil = {
      ...perfilNuevo(usuario.id, usuario.nombre_usuario, "admin", datos),
      email_verificado: true,
    };
    const completo = usuarioDe(perfil);
    const cuenta = db.cuentas.find((c) => c.usuario.id === usuario.id);
    if (cuenta) Object.assign(cuenta, { usuario: completo, perfil });
    const admin = db.administradores.find((a) => a.id === usuario.id);
    if (admin)
      Object.assign(admin, {
        nombres: datos.nombres,
        apellidos: datos.apellidos,
        estado: "activo",
      });
    sesion.set(completo);
    return response(200).json(completo);
  }),
];
