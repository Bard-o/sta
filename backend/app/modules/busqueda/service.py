"""Interfaz pública del módulo búsqueda (RF-27, RF-28, RF-29, RNF-01).

La consulta de vuelos vive en `vuelos.service` (la tabla es suya); aquí se validan los rangos,
se registra la búsqueda del cliente para la recomendación y se da forma a la respuesta del
contrato en `docs/api/iteracion-2.md`.
"""

from datetime import UTC, date, datetime, time
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.auth import UsuarioActual
from app.core.errors import DatosInvalidos
from app.core.security import Rol
from app.modules.busqueda.models import Busqueda
from app.modules.busqueda.schemas import (
    CiudadBusqueda,
    Clase,
    ClaseBusqueda,
    OrdenBusqueda,
    PaginaVuelosBusqueda,
    PromocionBusqueda,
    VueloBusqueda,
)
from app.modules.vuelos import service as vuelos_service
from app.modules.vuelos.service import (
    ClaseDetalleVuelo,
    FiltrosBusqueda,
    PaginaVuelosBuscados,
    VueloDetalleGestion,
)

_MENSAJE_RANGOS = "Revisa los rangos marcados."


class _CiudadLeida(Protocol):
    """Lo que la respuesta necesita de la ciudad del vuelo (HU-20)."""

    codigo: str
    nombre: str
    zona_horaria: str


def _validar_rangos(filtros: FiltrosBusqueda) -> None:
    """Rechaza los rangos sin sentido con `rango_invalido` y todos los campos que fallan.

    `vuelos.service.buscar_vuelos` no valida la coherencia de los rangos: esa es tarea de este
    módulo (docs/api/iteracion-2.md, HU-20).
    """
    campos: dict[str, str] = {}
    if (
        filtros.precio_min is not None
        and filtros.precio_max is not None
        and filtros.precio_min > filtros.precio_max
    ):
        campos["precio_max"] = "Debe ser mayor o igual que el precio mínimo."
    if (
        filtros.fecha_desde is not None
        and filtros.fecha_hasta is not None
        and filtros.fecha_hasta < filtros.fecha_desde
    ):
        campos["fecha_hasta"] = "La fecha final no puede ser anterior a la inicial."
    if (
        filtros.hora_desde is not None
        and filtros.hora_hasta is not None
        and filtros.hora_hasta < filtros.hora_desde
    ):
        campos["hora_hasta"] = "La hora final no puede ser anterior a la inicial."
    if (
        filtros.duracion_min is not None
        and filtros.duracion_max is not None
        and filtros.duracion_min > filtros.duracion_max
    ):
        campos["duracion_max"] = "Debe ser mayor o igual que la duración mínima."
    if campos:
        raise DatosInvalidos(_MENSAJE_RANGOS, codigo="rango_invalido", campos=campos)


def buscar_vuelos(
    db: Session,
    filtros: FiltrosBusqueda,
    *,
    usuario: UsuarioActual | None,
    orden: OrdenBusqueda = "precio",
    pagina: int = 1,
    por_pagina: int = 20,
    ahora: datetime | None = None,
) -> PaginaVuelosBusqueda:
    """Página de resultados de HU-20 y registro de la búsqueda del cliente (RF-29)."""
    _validar_rangos(filtros)
    resultados = vuelos_service.buscar_vuelos(
        db, filtros, orden=orden, pagina=pagina, por_pagina=por_pagina, ahora=ahora
    )
    if pagina == 1 and _registrar_busqueda(
        db,
        usuario=usuario,
        criterios=_criterios_de_filtros(filtros, orden),
        total=resultados.total,
        ahora=ahora,
    ):
        db.commit()
    return _a_pagina(resultados)


def buscar_regresos(
    db: Session,
    vuelo_ida_id: int,
    destino: str,
    fecha: date,
    *,
    usuario: UsuarioActual | None,
    clase: Clase | None = None,
    orden: OrdenBusqueda = "precio",
    pagina: int = 1,
    por_pagina: int = 20,
    ahora: datetime | None = None,
) -> PaginaVuelosBusqueda:
    """Regresos de la ida elegida (HU-21). Registra la primera página como en HU-20."""
    resultados = vuelos_service.regresos_de(
        db,
        vuelo_ida_id,
        destino,
        fecha,
        clase=clase,
        orden=orden,
        pagina=pagina,
        por_pagina=por_pagina,
        ahora=ahora,
    )
    if pagina == 1 and _registrar_busqueda(
        db,
        usuario=usuario,
        criterios=_criterios_de_regreso(vuelo_ida_id, destino, fecha, clase, orden),
        total=resultados.total,
        ahora=ahora,
    ):
        db.commit()
    return _a_pagina(resultados)


def _registrar_busqueda(
    db: Session,
    *,
    usuario: UsuarioActual | None,
    criterios: dict[str, Any],
    total: int,
    ahora: datetime | None = None,
) -> bool:
    """Guarda la búsqueda si la hizo un cliente; visitantes, admin y root no se registran.

    Devuelve True si insertó. Sin commit: lo confirma quien llama.
    """
    if usuario is None or usuario.rol != Rol.CLIENTE:
        return False
    db.add(
        Busqueda(
            usuario_id=usuario.id,
            criterios=criterios,
            total=total,
            registrada_en=ahora or datetime.now(UTC),
        )
    )
    db.flush()
    return True


def _criterios_de_filtros(filtros: FiltrosBusqueda, orden: OrdenBusqueda) -> dict[str, Any]:
    """Los parámetros de HU-20 que llegaron (sin None) y el orden, para la recomendación."""
    valores: dict[str, object] = {
        "codigo": filtros.codigo,
        "origen": filtros.origen,
        "destino": filtros.destino,
        "tipo": filtros.tipo,
        "fecha_desde": filtros.fecha_desde,
        "fecha_hasta": filtros.fecha_hasta,
        "hora_desde": filtros.hora_desde,
        "hora_hasta": filtros.hora_hasta,
        "duracion_min": filtros.duracion_min,
        "duracion_max": filtros.duracion_max,
        "precio_min": filtros.precio_min,
        "precio_max": filtros.precio_max,
        "clase": filtros.clase,
    }
    criterios = {clave: _a_json(valor) for clave, valor in valores.items() if valor is not None}
    criterios["orden"] = orden
    return criterios


def _criterios_de_regreso(
    vuelo_ida_id: int,
    destino: str,
    fecha: date,
    clase: Clase | None,
    orden: OrdenBusqueda,
) -> dict[str, Any]:
    """Los criterios de HU-21: el vuelo de ida, la ciudad y el día del regreso."""
    criterios: dict[str, Any] = {
        "vuelo_ida_id": vuelo_ida_id,
        "destino": destino,
        "fecha": fecha.isoformat(),
    }
    if clase is not None:
        criterios["clase"] = clase
    criterios["orden"] = orden
    return criterios


def _a_json(valor: object) -> object:
    """Fechas y horas en ISO 8601 dentro del JSONB (RF-15)."""
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    return valor


def _a_pagina(pagina: PaginaVuelosBuscados) -> PaginaVuelosBusqueda:
    return PaginaVuelosBusqueda(
        items=[_a_vuelo(item) for item in pagina.items],
        total=pagina.total,
        pagina=pagina.pagina,
        por_pagina=pagina.por_pagina,
    )


def _a_vuelo(detalle: VueloDetalleGestion) -> VueloBusqueda:
    """Un resultado de la búsqueda con el precio vigente y la disponibilidad por clase."""
    vuelo = detalle.vuelo
    return VueloBusqueda(
        id=vuelo.id,
        codigo=vuelo.codigo,
        tipo=vuelo.tipo,
        origen=_a_ciudad(detalle.origen),
        destino=_a_ciudad(detalle.destino),
        salida=vuelo.salida,
        llegada=vuelo.llegada,
        duracion_minutos=vuelo.duracion_minutos,
        economica=_a_clase(detalle.economica),
        primera=_a_clase(detalle.primera),
        agotado=detalle.economica.agotada and detalle.primera.agotada,
    )


def _a_ciudad(ciudad: _CiudadLeida) -> CiudadBusqueda:
    return CiudadBusqueda(
        codigo=ciudad.codigo, nombre=ciudad.nombre, zona_horaria=ciudad.zona_horaria
    )


def _a_clase(clase: ClaseDetalleVuelo) -> ClaseBusqueda:
    promocion = clase.promocion
    return ClaseBusqueda(
        precio_base=clase.precio_base,
        precio_vigente=clase.precio,
        promocion=(
            PromocionBusqueda(porcentaje=promocion.porcentaje, fin=promocion.fin)
            if promocion is not None
            else None
        ),
        disponibles=clase.disponibles,
        agotada=clase.agotada,
    )
