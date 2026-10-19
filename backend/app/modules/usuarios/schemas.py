from pydantic import BaseModel, ConfigDict, Field

from app.core.security import Rol


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=254, description="Nombre de usuario o correo")
    contrasena: str = Field(min_length=1, max_length=128)


class UsuarioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_usuario: str
    email: str | None
    rol: Rol
    email_verificado: bool
