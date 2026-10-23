"""Promociones por clase, precio vigente y vencimiento (HU-17, RF-23 a RF-26)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos, NoEncontrado
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.noticias.models import Noticia
from app.modules.reservas.service import OcupacionVuelo
from app.modules.vuelos import service
from app.modules.vuelos.models import Promocion
from app.modules.vuelos.schemas import PromocionEntrada
from app.modules.vuelos.tests.fabricas import (
    crear_promocion_bd,
    crear_vuelo,
    simular_ocupacion,
)

# Un instante fijo antes de todos los vuelos de los tests.
AHORA = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
SALIDA = datetime(2099, 1, 15, 10, 0, tzinfo=UTC)


def datos_promocion(**cambios: object) -> PromocionEntrada:
    base: dict[str, object] = {
        "porcentaje": 20,
        "clases": ["economica"],
        "inicio": AHORA - timedelta(hours=1),
        "fin": AHORA + timedelta(days=7),
    }
    base.update(cambios)
    return PromocionEntrada(**base)


# ---------- Creación, noticia y auditoría (HU-17, RF-23, RF-25, RF-26) ----------


def test_crear_promocion_publica_noticia_y_audita(db: Session, crear_usuario) -> None:
    """HU-17 · RF-25, RF-26: crear la promoción publica su noticia y deja la auditoría."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    usuario = crear_usuario()

    creada = service.crear_promocion(
        db, vuelo.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA
    )

    assert creada.estado == "vigente"
    assert creada.clases == ["economica"]
    assert creada.promocion.porcentaje == 20

    noticia = db.scalars(select(Noticia).where(Noticia.promocion_id == creada.promocion.id)).one()
    assert noticia.tipo == "promocion"
    assert noticia.promocion_estado == "programada"
    assert noticia.promocion_porcentaje == 20
    assert noticia.promocion_aplica_economica is True
    assert noticia.promocion_aplica_primera is False
    assert noticia.vigente is True

    auditoria = db.scalars(
        select(RegistroAuditoria).where(RegistroAuditoria.entidad_id == creada.promocion.id)
    ).one()
    assert auditoria.accion == "promocion.crear"
    assert auditoria.entidad == "promocion"
    assert auditoria.despues is not None
    assert auditoria.despues["porcentaje"] == 20
    assert auditoria.despues["clases"] == ["economica"]


def test_promocion_con_inicio_pasado_queda_vigente_de_inmediato(db: Session, crear_usuario) -> None:
    """HU-17 · RF-23: si `inicio` ya pasó, la promoción está vigente al crearse."""
    vuelo = crear_vuelo(db, salida=SALIDA)

    creada = service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(inicio=AHORA - timedelta(days=1)),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )

    assert creada.estado == "vigente"


def test_estados_programada_vigente_vencida_con_el_reloj_controlado(db: Session) -> None:
    """HU-17 · RF-23: la misma promoción pasa por programada, vigente y vencida."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    promocion = crear_promocion_bd(
        db,
        vuelo,
        inicio=AHORA,
        fin=AHORA + timedelta(hours=2),
    )

    assert service.estado_de(promocion, ahora=AHORA - timedelta(minutes=1)) == "programada"
    assert service.estado_de(promocion, ahora=AHORA + timedelta(hours=1)) == "vigente"
    assert service.estado_de(promocion, ahora=AHORA + timedelta(hours=3)) == "vencida"


def test_promocion_con_inicio_futuro_queda_programada(db: Session, crear_usuario) -> None:
    """HU-17 · RF-23: una promoción que empieza después está programada y no da descuento."""
    vuelo = crear_vuelo(db, salida=SALIDA)

    creada = service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(inicio=AHORA + timedelta(days=1), fin=AHORA + timedelta(days=3)),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )

    assert creada.estado == "programada"
    assert service.precio_vigente(db, vuelo.id, "economica", ahora=AHORA).promocion is None


def test_crear_promocion_en_vuelo_cancelado_o_salido_falla(db: Session, crear_usuario) -> None:
    """HU-17 · RF-23: solo se promocionan vuelos programados que no han salido."""
    cancelado = crear_vuelo(db, salida=SALIDA, estado="cancelado")
    salido = crear_vuelo(db, salida=AHORA - timedelta(hours=1))
    usuario = crear_usuario()

    with pytest.raises(service.VueloCerrado) as error_cancelado:
        service.crear_promocion(
            db, cancelado.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA
        )
    with pytest.raises(service.VueloCerrado):
        service.crear_promocion(
            db, salido.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA
        )

    assert error_cancelado.value.codigo == "vuelo_cerrado"


def test_crear_promocion_de_un_vuelo_inexistente_falla(db: Session, crear_usuario) -> None:
    """HU-17: un vuelo que no existe responde no_encontrado."""
    with pytest.raises(NoEncontrado) as error:
        service.crear_promocion(
            db, 999_999, datos_promocion(), usuario_id=crear_usuario().id, ahora=AHORA
        )

    assert error.value.codigo == "no_encontrado"


def test_crear_promocion_con_fin_no_posterior_al_inicio_falla(db: Session, crear_usuario) -> None:
    """HU-17 · RF-23: el fin debe ser posterior al inicio y futuro."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    usuario = crear_usuario()

    with pytest.raises(DatosInvalidos) as error:
        service.crear_promocion(
            db,
            vuelo.id,
            datos_promocion(inicio=AHORA + timedelta(days=2), fin=AHORA + timedelta(days=1)),
            usuario_id=usuario.id,
            ahora=AHORA,
        )
    assert error.value.campos == {"fin": "El fin debe ser posterior al inicio."}

    with pytest.raises(DatosInvalidos):
        service.crear_promocion(
            db,
            vuelo.id,
            datos_promocion(inicio=AHORA - timedelta(days=2), fin=AHORA - timedelta(days=1)),
            usuario_id=usuario.id,
            ahora=AHORA,
        )


# ---------- Duplicados por clase (RF-23) ----------


def test_no_se_acumulan_promociones_en_la_misma_clase(db: Session, crear_usuario) -> None:
    """HU-17 · RF-23: una segunda promoción para la misma clase choca con la activa."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    usuario = crear_usuario()
    service.crear_promocion(db, vuelo.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA)

    with pytest.raises(service.PromocionDuplicada) as error:
        service.crear_promocion(db, vuelo.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA)

    assert error.value.codigo == "promocion_duplicada"
    assert "clases" in error.value.campos


def test_promocion_de_otra_clase_si_se_puede_crear(db: Session, crear_usuario) -> None:
    """HU-17 · RF-23: economica y primera son independientes."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    usuario = crear_usuario()
    service.crear_promocion(
        db, vuelo.id, datos_promocion(clases=["economica"]), usuario_id=usuario.id, ahora=AHORA
    )

    creada = service.crear_promocion(
        db, vuelo.id, datos_promocion(clases=["primera"]), usuario_id=usuario.id, ahora=AHORA
    )

    assert creada.clases == ["primera"]


def test_una_promocion_vencida_libera_su_clase(db: Session, crear_usuario) -> None:
    """HU-17 · RF-23: al vencer, la clase vuelve a admitir otra promoción."""
    # La sesión real no hace autoflush: el flush explícito debe liberar el índice parcial.
    db.autoflush = False
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_promocion_bd(
        db,
        vuelo,
        inicio=AHORA - timedelta(days=2),
        fin=AHORA - timedelta(days=1),
    )

    creada = service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(inicio=AHORA - timedelta(hours=1)),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )

    assert creada.estado == "vigente"
    anterior = db.scalars(select(Promocion).where(Promocion.vuelo_id == vuelo.id)).all()
    assert [promocion.estado for promocion in anterior].count("vencida") == 1


# ---------- Precio vigente (RF-24) ----------


@pytest.mark.parametrize(
    ("precio_base", "porcentaje", "esperado"),
    [
        (280_000, 20, 224_000),
        (280_000, 15, 238_000),
        (750_000, 33, 502_500),
        (100, 1, 99),
        (101, 1, 99),  # 99.99 se redondea hacia abajo
    ],
)
def test_precio_con_descuento_redondea_hacia_abajo(
    precio_base: int, porcentaje: int, esperado: int
) -> None:
    """HU-17 · RF-24: el precio con descuento es entero, en COP, redondeado hacia abajo."""
    assert service.precio_con_descuento(precio_base, porcentaje) == esperado


def test_precio_vigente_aplica_solo_a_las_clases_promocionadas(db: Session, crear_usuario) -> None:
    """HU-17 · RF-24: la clase con promoción usa el descuento; la otra conserva su base."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(porcentaje=20, clases=["economica"]),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )

    economica = service.precio_vigente(db, vuelo.id, "economica", ahora=AHORA)
    primera = service.precio_vigente(db, vuelo.id, "primera", ahora=AHORA)

    assert economica.precio_base == 280_000
    assert economica.precio == 224_000
    assert economica.promocion is not None
    assert economica.promocion.porcentaje == 20
    assert primera.precio == 750_000
    assert primera.promocion is None


def test_precio_vigente_vuelve_al_base_al_vencer(db: Session, crear_usuario) -> None:
    """HU-17 · RF-24: pasada la hora de fin, el precio vuelve a la base."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_promocion_bd(
        db,
        vuelo,
        inicio=AHORA - timedelta(days=2),
        fin=AHORA - timedelta(hours=1),
    )

    precio = service.precio_vigente(db, vuelo.id, "economica", ahora=AHORA)

    assert precio.precio == 280_000
    assert precio.promocion is None


def test_un_tiquete_anterior_conserva_su_precio_sin_devoluciones(
    db: Session, crear_usuario
) -> None:
    """HU-17 · RF-24: la promoción no cambia el precio base, así que un tiquete comprado
    antes conserva el valor que pagó y no recibe devolución."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    precio_antes = (vuelo.precio_economica, vuelo.precio_primera)

    service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(porcentaje=50, clases=["economica", "primera"]),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )

    db.refresh(vuelo)
    assert (vuelo.precio_economica, vuelo.precio_primera) == precio_antes
    assert (
        service.precio_vigente(db, vuelo.id, "economica", ahora=AHORA).precio_base
        == (precio_antes[0])
    )


def test_precio_vigente_de_un_vuelo_inexistente_falla(db: Session) -> None:
    """HU-17 · RF-24: el detalle de un vuelo inexistente responde no_encontrado."""
    with pytest.raises(NoEncontrado):
        service.precio_vigente(db, 999_999, "economica", ahora=AHORA)


# ---------- Agotada (RF-23, RF-24) ----------


def test_promocion_de_dos_clases_sigue_vigente_mientras_quede_una_silla(
    db: Session, monkeypatch: pytest.MonkeyPatch, crear_usuario
) -> None:
    """HU-17 · RF-23: con dos clases, solo se agota cuando se agotan ambas."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    creada = service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(clases=["economica", "primera"]),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )
    simular_ocupacion(
        monkeypatch,
        {
            vuelo.id: OcupacionVuelo(
                vendidas_economica=vuelo.capacidad_economica,
                vendidas_primera=vuelo.capacidad_primera - 1,
            )
        },
    )

    agotadas = service.marcar_promociones_agotadas(db, vuelo.id, ahora=AHORA)

    assert agotadas == []
    assert creada.promocion.estado == "programada"


def test_promocion_se_agota_y_termina_su_noticia_al_no_quedar_sillas(
    db: Session, monkeypatch: pytest.MonkeyPatch, crear_usuario
) -> None:
    """HU-17 · RF-23, RF-25: sin sillas en sus clases, la promoción queda agotada y la
    noticia se retira del carrusel."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    creada = service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(clases=["economica", "primera"]),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )
    simular_ocupacion(
        monkeypatch,
        {
            vuelo.id: OcupacionVuelo(
                vendidas_economica=vuelo.capacidad_economica,
                vendidas_primera=vuelo.capacidad_primera,
            )
        },
    )

    agotadas = service.marcar_promociones_agotadas(db, vuelo.id, ahora=AHORA)

    assert agotadas == [creada.promocion.id]
    assert creada.promocion.estado == "agotada"
    noticia = db.scalars(select(Noticia).where(Noticia.promocion_id == creada.promocion.id)).one()
    assert noticia.promocion_estado == "agotada"
    assert noticia.vigente is False


def test_promocion_en_clase_ya_agotada_nace_agotada(
    db: Session, monkeypatch: pytest.MonkeyPatch, crear_usuario
) -> None:
    """HU-17 · RF-23: si la clase no tiene sillas al crear, no se ofrece una promoción falsa."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_ocupacion(
        monkeypatch,
        {
            vuelo.id: OcupacionVuelo(
                vendidas_economica=vuelo.capacidad_economica,
            )
        },
    )

    creada = service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(clases=["economica"]),
        usuario_id=crear_usuario().id,
        ahora=AHORA,
    )

    assert creada.estado == "agotada"
    assert service.precio_vigente(db, vuelo.id, "economica", ahora=AHORA).promocion is None


# ---------- Listado (HU-17) ----------


def test_listar_promociones_filtra_por_estado_efectivo(db: Session) -> None:
    """HU-17: el filtro usa el estado calculado: programada, vigente, vencida y agotada."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    programada = crear_promocion_bd(
        db,
        vuelo,
        clases=["economica"],
        inicio=AHORA + timedelta(days=1),
        fin=AHORA + timedelta(days=2),
    )
    vigente = crear_promocion_bd(
        db,
        vuelo,
        clases=["primera"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(days=1),
    )
    vencida = crear_promocion_bd(
        db,
        vuelo,
        clases=["economica"],
        inicio=AHORA - timedelta(days=2),
        fin=AHORA - timedelta(days=1),
        estado="vencida",
    )

    for estado, esperado in [
        ("programada", programada),
        ("vigente", vigente),
        ("vencida", vencida),
    ]:
        pagina = service.listar_promociones(db, estado=estado, ahora=AHORA)
        assert pagina.total == 1
        assert pagina.items[0].promocion.id == esperado.id
        assert pagina.items[0].estado == estado


def test_listar_promociones_pagina_y_trae_los_datos_del_vuelo(db: Session) -> None:
    """HU-17: el listado va de la más reciente a la más antigua y pagina."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    primera = crear_promocion_bd(db, vuelo, clases=["economica"])
    segunda = crear_promocion_bd(db, vuelo, clases=["primera"])
    # La primera promoción se creó antes; se fuerza el orden para no depender del reloj.
    primera.creada_en = AHORA - timedelta(hours=2)
    segunda.creada_en = AHORA - timedelta(hours=1)
    db.flush()

    pagina = service.listar_promociones(db, pagina=1, por_pagina=1, ahora=AHORA)

    assert pagina.total == 2
    assert pagina.pagina == 1
    assert pagina.por_pagina == 1
    assert [item.promocion.id for item in pagina.items] == [segunda.id]
    assert pagina.items[0].vuelo.id == vuelo.id
    assert pagina.items[0].origen.codigo == vuelo.origen_codigo
    assert pagina.items[0].destino.codigo == vuelo.destino_codigo


# ---------- Planificador (RF-23, RNF-18) ----------


def test_vencer_promociones_marca_todo_lo_vencido_y_es_idempotente(db: Session) -> None:
    """HU-17 · RF-23, RNF-18: la tarea vence todo lo atrasado y correrla otra vez no cambia nada."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    vencida = crear_promocion_bd(
        db, vuelo, inicio=AHORA - timedelta(days=2), fin=AHORA - timedelta(minutes=1)
    )
    vigente = crear_promocion_bd(
        db,
        vuelo,
        clases=["primera"],
        inicio=AHORA - timedelta(hours=1),
        fin=AHORA + timedelta(hours=1),
    )

    assert service.vencer_promociones(db, AHORA) == 1
    assert vencida.estado == "vencida"
    assert vigente.estado == "programada"
    assert service.vencer_promociones(db, AHORA) == 0


def test_la_tarea_vencer_promociones_esta_registrada() -> None:
    """HU-17 · RNF-18: el planificador conoce la tarea y la corre cada minuto."""
    from app.core.planificador import planificador

    assert "vuelos.vencer_promociones" in planificador.tareas
    assert planificador._tareas["vuelos.vencer_promociones"].cada == timedelta(minutes=1)
