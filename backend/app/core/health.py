"""GET /api/v1/health: el backend responde y alcanza la base de datos."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.db import DbSession

router = APIRouter(tags=["health"])


class Health(BaseModel):
    estado: Literal["ok"]
    base_de_datos: Literal["ok"]


@router.get("/health", response_model=Health)
def health(db: DbSession) -> Health:
    db.execute(text("SELECT 1"))
    return Health(estado="ok", base_de_datos="ok")
