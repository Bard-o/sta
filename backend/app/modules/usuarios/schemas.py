"""Contrato del módulo usuarios (docs/api/iteracion-1.md, HU-01 a HU-12)."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.security import Rol

# CC: cédula de ciudadanía · TI: tarjeta de identidad · RC: registro civil
# CE: cédula de extranjería · PA: pasaporte (RF-03).
TipoDocumento = Literal["CC", "TI", "RC", "CE", "PA"]
Genero = Literal["femenino", "masculino", "otro"]
EstadoAdministrador = Literal["activo", "inactivo", "registro_incompleto"]

PATRON_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PATRON_NOMBRE_USUARIO = r"^[A-Za-z0-9._-]{3,50}$"
# Alfanumérico, sin espacios ni puntos (RF-03).
PATRON_DOCUMENTO = r"^[A-Za-z0-9]{3,20}$"
PATRON_TELEFONO = r"^[0-9 +()-]{7,20}$"

Contrasena = Annotated[str, Field(min_length=1, max_length=128)]


# ---------- Sesión (HU-03, HU-04) ----------


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=254, description="Nombre de usuario o correo")
    contrasena: Contrasena


class UsuarioSalida(BaseModel):
    # Los campos con valor por defecto igual figuran como requeridos en los tipos generados.
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )

    id: int
    nombre_usuario: str
    email: str | None
    rol: Rol
    email_verificado: bool
    # HU-12: un administrador con el registro incompleto solo puede completar su registro.
    # Hasta que usuarios guarde este dato, todas las cuentas existentes lo tienen completo.
    registro_completo: bool = True
    # Para el saludo del menú. El root y el administrador sin registro completo no tienen nombre.
    nombres: str | None = None
    apellidos: str | None = None


# ---------- Datos personales (HU-01, HU-07, HU-12) ----------


class DatosEditables(BaseModel):
    """Datos que el titular puede cambiar desde su perfil (RF-08)."""

    nombres: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    fecha_nacimiento: date = Field(description="No puede ser futura.")
    lugar_nacimiento: str = Field(min_length=1, max_length=120)
    direccion_facturacion: str = Field(min_length=1, max_length=200)
    genero: Genero
    email: str = Field(max_length=254, pattern=PATRON_EMAIL)
    telefono: str | None = Field(default=None, pattern=PATRON_TELEFONO)


class DatosPersonalesEntrada(DatosEditables):
    tipo_documento: TipoDocumento
    numero_documento: str = Field(pattern=PATRON_DOCUMENTO)


class RegistroClienteEntrada(DatosPersonalesEntrada):
    """HU-01. La imagen de perfil se sube después con PUT /usuarios/me/imagen."""

    nombre_usuario: str = Field(pattern=PATRON_NOMBRE_USUARIO)
    contrasena: Contrasena
    acepta_politica: bool = Field(description="Debe ser true (Ley 1581 de 2012).")


class PerfilEntrada(DatosEditables):
    """HU-07. El documento y el nombre de usuario no se editan."""


class PerfilSalida(BaseModel):
    id: int
    nombre_usuario: str
    rol: Literal["cliente", "admin"]
    tipo_documento: TipoDocumento
    numero_documento: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    lugar_nacimiento: str
    direccion_facturacion: str
    genero: Genero
    email: str = Field(description="Correo vigente de la cuenta.")
    email_verificado: bool
    email_pendiente: str | None = Field(
        description="Correo nuevo que espera verificación (HU-07); mientras tanto sigue `email`."
    )
    telefono: str | None
    imagen_url: str | None
    suscrito_noticias: bool = Field(description="Siempre false para administradores.")


# ---------- Correo y contraseña (HU-02, HU-05, HU-06) ----------


class TokenEntrada(BaseModel):
    """Token de un enlace enviado por correo (verificación o baja de noticias)."""

    token: str = Field(min_length=1, max_length=512)


class RestablecimientoSolicitud(BaseModel):
    email: str = Field(max_length=254, pattern=PATRON_EMAIL)


class RestablecimientoConfirmacion(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    contrasena_nueva: Contrasena
    confirmacion: Contrasena


class CambioContrasenaEntrada(BaseModel):
    contrasena_actual: Contrasena
    contrasena_nueva: Contrasena
    confirmacion: Contrasena


class MensajeSalida(BaseModel):
    mensaje: str


# ---------- Suscripción y desactivación (HU-08, HU-09) ----------


class SuscripcionEntrada(BaseModel):
    noticias: bool


class SuscripcionSalida(BaseModel):
    noticias: bool


class BloqueoDesactivacion(BaseModel):
    tipo: Literal["compra", "reserva"]
    codigo_reserva: str | None = Field(description="Código de la compra; null en una reserva.")
    vuelo_id: int
    vuelo_codigo: str
    origen: str
    destino: str
    salida: datetime


class DesactivacionSalida(BaseModel):
    puede_desactivar: bool
    bloqueos: list[BloqueoDesactivacion] = Field(
        description="Tiquetes o reservas activas en vuelos futuros que impiden desactivar (HU-09)."
    )


# ---------- Administradores (HU-10, HU-11, HU-12) ----------


class AdministradorEntrada(BaseModel):
    nombre_usuario: str = Field(pattern=PATRON_NOMBRE_USUARIO)
    contrasena_temporal: Contrasena


class AdministradorSalida(BaseModel):
    id: int
    nombre_usuario: str
    nombres: str | None = Field(description="null mientras el registro esté incompleto.")
    apellidos: str | None
    estado: EstadoAdministrador
    creado_en: datetime


class RegistroAdministradorEntrada(DatosPersonalesEntrada):
    """HU-12: mismos datos del cliente más el cambio de la contraseña temporal."""

    contrasena_temporal: Contrasena
    contrasena_nueva: Contrasena
    confirmacion: Contrasena
