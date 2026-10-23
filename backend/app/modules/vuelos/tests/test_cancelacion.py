"""Cancelación de un vuelo sin ventas (HU-16, RF-19, RF-26)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NoEncontrado
from app.core.security import Rol
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.noticias import service as noticias_service
from app.modules.noticias.models import Noticia
from app.modules.reservas import service as reservas_service
from app.modules.reservas.service import OcupacionVuelo
from app.modules.vuelos import service
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.schemas import PromocionEntrada, VueloEntrada
from app.modules.vuelos.tests.fabricas import (
    crear_promocion_bd,
    crear_vuelo,
    simular_ocupacion,
)

# Un instante fijo antes de la salida de todos los vuelos de los tests.
AHORA = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
# La salida lejana deja margen para cancelar y volver a programar la misma ruta.
SALIDA = datetime(2099, 1, 15, 10, 0, tzinfo=UTC)


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
        "inicio": AHORA - timedelta(hours=1),
        "fin": AHORA + timedelta(days=7),
    }
    base.update(cambios)
    return PromocionEntrada(**base)


def simular_anulacion(monkeypatch: pytest.MonkeyPatch, *, total: int = 0) -> list[int]:
    """Sustituye la anulación de reservas de la iteración 2 y registra sus llamadas."""
    llamadas: list[int] = []

    def _anular(_db: Session, vuelo_id: int) -> int:
        llamadas.append(vuelo_id)
        return total

    monkeypatch.setattr(reservas_service, "anular_reservas_de_vuelo", _anular)
    return llamadas


# ---------- Cancelación (HU-16, RF-19) ----------


def test_cancelar_marca_el_vuelo_cancelado_y_conserva_el_codigo(
    db: Session, crear_usuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-16 · RF-19: cancelar deja el vuelo `cancelado` y conserva su código (SUP-01)."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, salida=SALIDA)
    codigo = vuelo.codigo
    simular_anulacion(monkeypatch)

    resultado = service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    assert resultado.vuelo.vuelo.estado == "cancelado"
    assert resultado.vuelo.vuelo.codigo == codigo
    assert resultado.vuelo.editable is False
    assert resultado.vuelo.cancelable is False
    assert resultado.vuelo.ocupacion == OcupacionVuelo()
    assert resultado.reservas_anuladas == 0


def test_cancelar_anula_las_reservas_y_cuenta_los_avisos(
    db: Session, crear_usuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-16: las reservas activas se anulan (y sus clientes reciben el aviso), sin bloquear."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_ocupacion(
        monkeypatch,
        {vuelo.id: OcupacionVuelo(reservas_activas=2, reservadas_economica=2)},
    )
    llamadas = simular_anulacion(monkeypatch, total=2)

    resultado = service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    assert llamadas == [vuelo.id]
    assert resultado.reservas_anuladas == 2


def test_cancelar_con_tiquetes_vendidos_falla_con_vuelo_con_tiquetes(
    db: Session, crear_usuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-16 · RF-19: con tiquetes vendidos no se cancela y se indica la fuerza mayor."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_ocupacion(monkeypatch, {vuelo.id: OcupacionVuelo(vendidas_economica=1)})

    with pytest.raises(service.VueloConTiquetes) as error:
        service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    assert error.value.codigo == "vuelo_con_tiquetes"
    assert error.value.mensaje == (
        "El vuelo tiene tiquetes vendidos; requiere cancelación por fuerza mayor."
    )
    assert vuelo.estado == "programado"
    auditados = db.scalar(
        select(func.count(RegistroAuditoria.id)).where(RegistroAuditoria.accion == "vuelo.cancelar")
    )
    assert auditados == 0


@pytest.mark.parametrize(
    ("estado", "salida"),
    [
        ("realizado", SALIDA),
        ("cancelado", SALIDA),
        ("programado", datetime(2026, 10, 19, 10, 0, tzinfo=UTC)),
    ],
)
def test_cancelar_un_vuelo_cerrado_falla_con_vuelo_cerrado(
    db: Session,
    crear_usuario,
    monkeypatch: pytest.MonkeyPatch,
    estado: str,
    salida: datetime,
) -> None:
    """HU-16 · RF-19: un vuelo realizado, cancelado o que ya salió no se cancela."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, estado=estado, salida=salida)
    simular_anulacion(monkeypatch)

    with pytest.raises(service.VueloCerrado) as error:
        service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    assert error.value.codigo == "vuelo_cerrado"
    assert vuelo.estado == estado


def test_cancelar_un_vuelo_inexistente(db: Session, crear_usuario) -> None:
    """HU-16: un vuelo que no existe responde `no_encontrado`."""
    usuario = crear_usuario(Rol.ADMIN)

    with pytest.raises(NoEncontrado) as error:
        service.cancelar_vuelo(db, 999_999, usuario_id=usuario.id, ahora=AHORA)

    assert error.value.codigo == "no_encontrado"


# ---------- Efectos en noticias y promociones (HU-16, RF-23, RF-25) ----------


def test_cancelar_saca_el_vuelo_del_carrusel_y_retira_sus_noticias(
    db: Session, crear_usuario
) -> None:
    """HU-16: tras cancelar, el vuelo y su promoción salen del carrusel y quedan no vigentes."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = service.programar_vuelo(db, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA).vuelo
    service.crear_promocion(db, vuelo.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA)
    assert noticias_service.carrusel(db, ahora=AHORA)

    service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    assert noticias_service.carrusel(db, ahora=AHORA) == []
    noticias = noticias_service.listar_noticias(db, ahora=AHORA).items
    assert len(noticias) == 2
    assert all(noticia.vigente is False for noticia in noticias)


def test_cancelar_pasa_a_cancelada_solo_las_promociones_activas(db: Session, crear_usuario) -> None:
    """HU-16 · RF-23, RF-25: las promociones vigentes o programadas pasan a `cancelada`."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = service.programar_vuelo(db, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA).vuelo
    vigente = service.crear_promocion(
        db, vuelo.id, datos_promocion(), usuario_id=usuario.id, ahora=AHORA
    )
    programada = service.crear_promocion(
        db,
        vuelo.id,
        datos_promocion(
            clases=["primera"],
            inicio=AHORA + timedelta(hours=1),
            fin=AHORA + timedelta(days=2),
        ),
        usuario_id=usuario.id,
        ahora=AHORA,
    )
    vencida = crear_promocion_bd(
        db,
        vuelo,
        clases=["economica"],
        inicio=AHORA - timedelta(days=2),
        fin=AHORA - timedelta(days=1),
        estado="vencida",
    )

    service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    assert vigente.promocion.estado == "cancelada"
    assert programada.promocion.estado == "cancelada"
    assert vencida.estado == "vencida"
    for creada in (vigente, programada):
        noticia = db.scalars(
            select(Noticia).where(Noticia.promocion_id == creada.promocion.id)
        ).one()
        assert noticia.vigente is False
        assert noticia.promocion_estado == "cancelada"


# ---------- Código, auditoría y transacción (HU-16, RF-26, RNF-17) ----------


def test_cancelar_libera_la_ruta_sin_reutilizar_el_codigo(db: Session, crear_usuario) -> None:
    """HU-16 · SUP-01: el código no se reutiliza y la ruta queda libre para un vuelo nuevo."""
    usuario = crear_usuario(Rol.ADMIN)
    original = service.programar_vuelo(db, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA).vuelo
    codigo = original.codigo

    service.cancelar_vuelo(db, original.id, usuario_id=usuario.id, ahora=AHORA)
    nuevo = service.programar_vuelo(db, datos_vuelo(), usuario_id=usuario.id, ahora=AHORA).vuelo

    assert nuevo.id != original.id
    assert nuevo.codigo != codigo
    assert original.codigo == codigo


def test_cancelar_deja_la_auditoria_ligera(
    db: Session, crear_usuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-16 · RF-26: la cancelación queda en la auditoría con el cambio y las anulaciones."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_anulacion(monkeypatch, total=2)

    service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    registro = db.scalars(
        select(RegistroAuditoria).where(RegistroAuditoria.accion == "vuelo.cancelar")
    ).one()
    assert registro.entidad == "vuelo"
    assert registro.entidad_id == vuelo.id
    assert registro.usuario_id == usuario.id
    assert registro.antes == {"estado": "programado"}
    assert registro.despues == {
        "estado": "cancelado",
        "reservas_anuladas": 2,
        "promociones_canceladas": [],
    }


def test_cancelar_no_hace_commit(
    db: Session, crear_usuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HU-16 · RNF-17: la cancelación usa la transacción de quien llama; el commit es del router."""
    usuario = crear_usuario(Rol.ADMIN)
    vuelo = crear_vuelo(db, salida=SALIDA)
    simular_anulacion(monkeypatch)
    db.execute(select(Vuelo.id).limit(0))
    transaccion = db.get_transaction()

    service.cancelar_vuelo(db, vuelo.id, usuario_id=usuario.id, ahora=AHORA)

    assert db.get_transaction() is transaccion
