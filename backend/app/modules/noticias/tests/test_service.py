"""Funciones públicas de noticias (HU-19, RF-22, RF-25, RF-55, RF-56, RNF-17)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.modules.noticias import service
from app.modules.noticias.models import Noticia
from app.modules.noticias.service import CiudadPublicada
from app.modules.noticias.tests.fabricas import promocion_publicada, vuelo_publicado


def _noticias(db: Session) -> list[Noticia]:
    return list(db.scalars(select(Noticia).order_by(Noticia.id)))


def test_publicar_noticia_vuelo_copia_los_datos_del_vuelo(db: Session):
    """RF-22 · HU-13: Pereira → Miami publica la noticia con la imagen de Miami (SUP-30)."""
    service.publicar_noticia_vuelo(db, vuelo_publicado())

    (noticia,) = _noticias(db)
    assert noticia.tipo == "vuelo"
    assert noticia.titulo == "Nuevo vuelo Pereira → Miami"
    assert noticia.publicada_en is not None
    assert noticia.vigente is True
    assert noticia.vuelo_id == 76
    assert noticia.vuelo_codigo == "STA-00076"
    assert noticia.origen_codigo == "PEI"
    assert noticia.origen_nombre == "Pereira"
    assert noticia.origen_zona_horaria == "America/Bogota"
    assert noticia.destino_codigo == "MIA"
    assert noticia.destino_nombre == "Miami"
    assert noticia.destino_zona_horaria == "America/New_York"
    assert noticia.salida == datetime(2026, 11, 15, 14, 30, tzinfo=UTC)
    assert noticia.precio_economica == 1_980_000
    assert noticia.precio_primera == 4_500_000
    assert noticia.imagen_url == "/imagenes/ciudades/MIA.jpg"
    # La noticia de un vuelo no lleva datos de promoción.
    assert noticia.promocion_id is None
    assert noticia.promocion_estado is None


def test_publicar_noticia_vuelo_deja_el_punto_de_encolado_del_correo(
    db: Session, monkeypatch: pytest.MonkeyPatch
):
    """RF-56: publicar deja listo el encolado del correo a los suscritos (issue #32)."""
    noticias_enviadas: list[Noticia] = []
    monkeypatch.setattr(
        service,
        "_encolar_correo_suscriptores",
        lambda _db, noticia: noticias_enviadas.append(noticia),
    )

    service.publicar_noticia_vuelo(db, vuelo_publicado())

    assert len(noticias_enviadas) == 1
    assert noticias_enviadas[0].id is not None
    assert noticias_enviadas[0].tipo == "vuelo"


def test_publicar_noticia_promocion_copia_los_datos(db: Session):
    """RF-25 · HU-17: la promoción publica su noticia con vuelo, descuento y vigencia."""
    promocion = promocion_publicada(clases=("economica", "primera"))

    service.publicar_noticia_promocion(db, promocion)

    (noticia,) = _noticias(db)
    assert noticia.tipo == "promocion"
    assert noticia.titulo == "Promoción del 30 % en Pereira → Miami, económica y primera"
    assert noticia.vigente is True
    assert noticia.promocion_id == 12
    assert noticia.promocion_porcentaje == 30
    assert noticia.promocion_aplica_economica is True
    assert noticia.promocion_aplica_primera is True
    assert noticia.promocion_inicio == promocion.inicio
    assert noticia.promocion_fin == promocion.fin
    assert noticia.promocion_estado == "programada"
    # Copia el vuelo para no consultarlo nunca (RF-22).
    assert noticia.vuelo_id == 76
    assert noticia.vuelo_codigo == "STA-00076"
    assert noticia.precio_economica == 1_980_000
    assert noticia.imagen_url == "/imagenes/ciudades/MIA.jpg"


def test_publicar_noticia_promocion_de_una_sola_clase(db: Session):
    """RF-25: el título nombra solo la clase a la que aplica la promoción."""
    service.publicar_noticia_promocion(db, promocion_publicada(clases=("primera",)))

    (noticia,) = _noticias(db)
    assert noticia.titulo == "Promoción del 30 % en Pereira → Miami, primera"
    assert noticia.promocion_aplica_economica is False
    assert noticia.promocion_aplica_primera is True


def test_publicar_noticia_promocion_tambien_deja_el_punto_de_encolado(
    db: Session, monkeypatch: pytest.MonkeyPatch
):
    """RF-56: cada noticia publicada pasa por el encolado del correo (issue #32)."""
    noticias_enviadas: list[Noticia] = []
    monkeypatch.setattr(
        service,
        "_encolar_correo_suscriptores",
        lambda _db, noticia: noticias_enviadas.append(noticia),
    )

    service.publicar_noticia_promocion(db, promocion_publicada())

    assert [noticia.tipo for noticia in noticias_enviadas] == ["promocion"]


def test_actualizar_noticias_de_vuelo_actualiza_vuelo_y_promocion(db: Session):
    """HU-15: al editar el vuelo se actualizan los datos copiados en todas sus noticias."""
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    service.publicar_noticia_promocion(db, promocion_publicada())

    editado = vuelo_publicado(
        origen=CiudadPublicada(codigo="BOG", nombre="Bogotá", zona_horaria="America/Bogota"),
        destino=CiudadPublicada(codigo="MAD", nombre="Madrid", zona_horaria="Europe/Madrid"),
        salida=datetime(2026, 12, 1, 9, 0, tzinfo=UTC),
        precio_economica=2_100_000,
        precio_primera=4_900_000,
        imagen_url="/imagenes/ciudades/MAD.jpg",
    )
    service.actualizar_noticias_de_vuelo(db, editado)

    noticia_vuelo, noticia_promocion = _noticias(db)
    for noticia in (noticia_vuelo, noticia_promocion):
        assert noticia.origen_codigo == "BOG"
        assert noticia.origen_nombre == "Bogotá"
        assert noticia.destino_codigo == "MAD"
        assert noticia.destino_nombre == "Madrid"
        assert noticia.salida == datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
        assert noticia.precio_economica == 2_100_000
        assert noticia.precio_primera == 4_900_000
        assert noticia.imagen_url == "/imagenes/ciudades/MAD.jpg"

    assert noticia_vuelo.titulo == "Nuevo vuelo Bogotá → Madrid"
    assert noticia_promocion.titulo == "Promoción del 30 % en Bogotá → Madrid, económica"
    # Los datos propios de la promoción no cambian.
    assert noticia_promocion.promocion_porcentaje == 30
    assert noticia_promocion.promocion_estado == "programada"
    assert noticia_promocion.vigente is True


def test_retirar_noticias_de_vuelo_las_deja_no_vigentes(db: Session):
    """HU-16 · HU-18: cancelar o realizar el vuelo retira su noticia y la de su promoción."""
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    service.publicar_noticia_promocion(db, promocion_publicada())

    service.retirar_noticias_de_vuelo(db, 76)

    assert [noticia.vigente for noticia in _noticias(db)] == [False, False]


@pytest.mark.parametrize("estado", ["agotada", "cancelada"])
def test_terminar_noticia_promocion_la_deja_no_vigente(db: Session, estado: str):
    """RF-23 · RF-25: agotar o cancelar la promoción deja su noticia como no vigente."""
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    service.publicar_noticia_promocion(db, promocion_publicada())

    service.terminar_noticia_promocion(db, 12, estado)

    noticia_vuelo, noticia_promocion = _noticias(db)
    assert noticia_promocion.vigente is False
    assert noticia_promocion.promocion_estado == estado
    assert noticia_vuelo.vigente is True
    assert noticia_vuelo.promocion_estado is None


def test_terminar_noticia_promocion_solo_afecta_a_su_promocion(db: Session):
    """RF-25: cada promoción tiene su noticia; terminar una no toca a las demás."""
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    service.publicar_noticia_promocion(db, promocion_publicada())
    service.publicar_noticia_promocion(
        db, promocion_publicada(promocion_id=13, clases=("primera",))
    )

    service.terminar_noticia_promocion(db, 12, "agotada")

    _, economica, primera = _noticias(db)
    assert economica.promocion_estado == "agotada"
    assert primera.promocion_estado == "programada"
    assert primera.vigente is True


def test_una_promocion_vencida_por_fecha_no_se_marca_al_publicar(db: Session):
    """RF-25: el vencimiento por fecha se calcula al consultar (lo hace el issue #17)."""
    vencida = promocion_publicada(
        inicio=datetime(2020, 1, 1, tzinfo=UTC),
        fin=datetime(2020, 1, 2, tzinfo=UTC),
    )

    service.publicar_noticia_promocion(db, vencida)

    (noticia,) = _noticias(db)
    assert noticia.vigente is True
    assert noticia.promocion_estado == "programada"


def test_ninguna_funcion_hace_commit(db: Session):
    """RNF-17: las funciones van en la transacción de quien llama y no la cierran."""
    # Fuerza el inicio de la transacción de la sesión.
    db.execute(select(Noticia.id).limit(0))
    transaccion = db.get_transaction()

    service.publicar_noticia_vuelo(db, vuelo_publicado())
    assert db.get_transaction() is transaccion
    service.publicar_noticia_promocion(db, promocion_publicada())
    assert db.get_transaction() is transaccion
    service.actualizar_noticias_de_vuelo(db, vuelo_publicado(precio_economica=2_000_000))
    assert db.get_transaction() is transaccion
    service.retirar_noticias_de_vuelo(db, 76)
    assert db.get_transaction() is transaccion
    service.terminar_noticia_promocion(db, 12, "cancelada")
    assert db.get_transaction() is transaccion


def test_el_rollback_del_llamador_no_deja_noticias(db: Session):
    """RNF-17: si la transacción del vuelo o la promoción se revierte, no queda nada."""
    service.publicar_noticia_vuelo(db, vuelo_publicado())
    service.publicar_noticia_promocion(db, promocion_publicada())

    db.rollback()

    assert _noticias(db) == []


def test_las_funciones_no_consultan_la_tabla_de_vuelos(db: Session):
    """RF-22 · RF-25: noticias nunca consulta vuelos; vuelos le avisa de cada cambio."""
    sentencias: list[str] = []

    def capturar(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        sentencias.append(statement.lower())

    motor = db.get_bind()
    event.listen(motor, "before_cursor_execute", capturar)
    try:
        service.publicar_noticia_vuelo(db, vuelo_publicado())
        service.publicar_noticia_promocion(db, promocion_publicada())
        service.actualizar_noticias_de_vuelo(db, vuelo_publicado())
        service.retirar_noticias_de_vuelo(db, 76)
        service.terminar_noticia_promocion(db, 12, "agotada")
        db.flush()
    finally:
        event.remove(motor, "before_cursor_execute", capturar)

    assert sentencias
    assert all("vuelos" not in sentencia for sentencia in sentencias)


def test_retirar_y_terminar_no_fallan_si_no_hay_noticias(db: Session):
    """HU-16 · RF-25: las funciones son idempotentes dentro de la transacción del llamador."""
    service.retirar_noticias_de_vuelo(db, 999)
    service.terminar_noticia_promocion(db, 999, "cancelada")

    assert _noticias(db) == []
