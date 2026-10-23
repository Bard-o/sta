"""Paso automático a realizado y sus efectos en el vuelo (HU-18, RF-21, RNF-18)."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.planificador import planificador
from app.core.security import Rol
from app.modules.noticias.models import Noticia
from app.modules.vuelos import service
from app.modules.vuelos.schemas import PromocionEntrada, VueloEntrada
from app.modules.vuelos.tests.fabricas import crear_vuelo

# Reloj fijo de los tests: los vuelos de 50 minutos que salieron hace una hora ya llegaron.
AHORA = datetime(2026, 12, 10, 12, 0, tzinfo=UTC)


def datos_vuelo(**cambios: object) -> VueloEntrada:
    base: dict[str, object] = {
        "origen": "PEI",
        "destino": "BOG",
        "fecha_salida": date(2099, 1, 15),
        "hora_salida": time(10, 0),
        "duracion_minutos": 50,
        "precio_economica": 280_000,
        "precio_primera": 750_000,
    }
    base.update(cambios)
    return VueloEntrada(**base)


def datos_promocion(**cambios: object) -> PromocionEntrada:
    base: dict[str, object] = {
        "porcentaje": 20,
        "clases": ["economica"],
        "inicio": AHORA + timedelta(days=1),
        "fin": AHORA + timedelta(days=7),
    }
    base.update(cambios)
    return PromocionEntrada(**base)


def test_marca_realizado_el_vuelo_cuya_llegada_ya_paso(db: Session) -> None:
    """HU-18 · criterio 1 · RF-21, RNF-18: como máximo 2 minutos después de la llegada el vuelo
    pasa a realizado; el que aún no ha llegado sigue programado."""
    llego = crear_vuelo(db, salida=AHORA - timedelta(hours=1), duracion_minutos=50, tipo="nacional")
    en_vuelo = crear_vuelo(
        db,
        origen="BOG",
        destino="MDE",
        salida=AHORA - timedelta(minutes=10),
        duracion_minutos=50,
    )

    assert service.marcar_realizados(db, AHORA) == 1
    assert llego.estado == "realizado"
    assert en_vuelo.estado == "programado"


def test_procesa_lo_que_vencio_con_el_servidor_apagado(db: Session) -> None:
    """HU-18 · criterio 2 · RNF-18: al arrancar marca todos los vuelos que llegaron durante la
    caída y correr la tarea otra vez no cambia nada."""
    primero = crear_vuelo(db, salida=AHORA - timedelta(days=2), duracion_minutos=60)
    segundo = crear_vuelo(
        db,
        origen="BOG",
        destino="MDE",
        salida=AHORA - timedelta(days=1),
        duracion_minutos=60,
    )

    assert service.marcar_realizados(db, AHORA) == 2
    assert primero.estado == "realizado"
    assert segundo.estado == "realizado"
    assert service.marcar_realizados(db, AHORA) == 0


def test_no_toca_los_cancelados_ni_los_que_no_han_llegado(db: Session) -> None:
    """HU-18 · RF-21: solo pasan a realizado los programados cuya llegada ya pasó."""
    cancelado = crear_vuelo(
        db, estado="cancelado", salida=AHORA - timedelta(days=1), duracion_minutos=60
    )
    futuro = crear_vuelo(
        db,
        origen="BOG",
        destino="MDE",
        salida=AHORA + timedelta(hours=1),
        duracion_minutos=60,
    )

    assert service.marcar_realizados(db, AHORA) == 0
    assert cancelado.estado == "cancelado"
    assert futuro.estado == "programado"


def test_al_pasar_a_realizado_retira_las_noticias_del_vuelo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-18 · criterio 4: al pasar a realizado se llama a noticias.retirar_noticias_de_vuelo y
    el vuelo sale del carrusel."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = service.programar_vuelo(
        db, datos_vuelo(fecha_salida=date(2026, 12, 10)), usuario_id=usuario.id
    ).vuelo
    noticia = db.scalar(select(Noticia).where(Noticia.vuelo_id == vuelo.id))
    assert noticia is not None
    assert noticia.vigente is True

    # Llegada a las 15:50 UTC del 10/12/2026 (10:00 en Bogotá más 50 minutos).
    assert service.marcar_realizados(db, datetime(2026, 12, 10, 20, 0, tzinfo=UTC)) == 1
    db.flush()
    db.refresh(noticia)
    assert noticia.vigente is False


def test_un_vuelo_realizado_no_se_edita_ni_cancela_ni_recibe_promociones(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-18 · criterio 4 · RF-18, RF-23: un vuelo realizado responde vuelo_cerrado al editar,
    cancelar o crear promociones."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, salida=AHORA - timedelta(hours=2), duracion_minutos=60)
    assert service.marcar_realizados(db, AHORA) == 1

    with pytest.raises(service.VueloCerrado) as al_editar:
        service.editar_vuelo(db, vuelo.id, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA)
    assert al_editar.value.codigo == "vuelo_cerrado"

    with pytest.raises(service.VueloCerrado) as al_cancelar:
        service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)
    assert al_cancelar.value.codigo == "vuelo_cerrado"

    with pytest.raises(service.VueloCerrado) as al_promocionar:
        service.crear_promocion(db, vuelo.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA)
    assert al_promocionar.value.codigo == "vuelo_cerrado"


def test_sale_del_listado_programado_y_entra_en_el_de_realizados(db: Session) -> None:
    """HU-18 · criterio 1 · RF-21: el vuelo deja de ofrecerse como programado y aparece en los
    realizados (la búsqueda pública todavía no existe)."""
    vuelo = crear_vuelo(db, salida=AHORA - timedelta(hours=2), duracion_minutos=60)

    assert service.marcar_realizados(db, AHORA) == 1

    programados = service.listar_vuelos_gestion(db, estado="programado", ahora=AHORA)
    realizados = service.listar_vuelos_gestion(db, estado="realizado", ahora=AHORA)
    assert programados.items == []
    assert [item.vuelo.id for item in realizados.items] == [vuelo.id]


def test_la_tarea_marcar_realizados_esta_registrada() -> None:
    """HU-18 · RNF-18: el planificador conoce la tarea y la corre cada minuto."""
    assert "vuelos.marcar_realizados" in planificador.tareas
    assert planificador._tareas["vuelos.marcar_realizados"].cada == timedelta(minutes=1)
