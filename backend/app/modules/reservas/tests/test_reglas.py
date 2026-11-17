"""Reglas de los viajeros (RF-31 a RF-35, HU-24, HU-25 y HU-26)."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos
from app.core.security import Rol
from app.modules.reservas import service
from app.modules.reservas.models import Tiquete
from app.modules.reservas.sillas import SillasInsuficientes
from app.modules.reservas.tests.fabricas import (
    crear_compra,
    crear_reserva,
    datos_viajero,
)
from app.modules.vuelos.tests.fabricas import crear_vuelo

# Vuelo de prueba con una fecha en la que ya existen viajeros mayores y menores.
SALIDA = datetime(2027, 6, 1, 10, 0, tzinfo=UTC)
HOY = date(2026, 11, 16)


@pytest.mark.parametrize(
    "campo",
    [
        "tipo_documento",
        "numero_documento",
        "nombres",
        "apellidos",
        "telefono",
        "email",
        "contacto_nombre",
        "contacto_telefono",
    ],
)
def test_rf31_un_campo_obligatorio_vacio_se_reporta_en_su_viajero(campo: str) -> None:
    """RF-31 · HU-24: un campo obligatorio vacío rechaza la reserva o compra y la ruta del
    error apunta al viajero y al campo."""
    with pytest.raises(DatosInvalidos) as error:
        service.validar_viajeros([datos_viajero(**{campo: "   "})], hoy=HOY)

    assert error.value.codigo == "datos_invalidos"
    assert f"viajeros.0.{campo}" in (error.value.campos or {})


def test_rf31_un_correo_con_formato_invalido_se_rechaza() -> None:
    """RF-31 · HU-24: un correo con formato inválido se rechaza en el campo del viajero."""
    with pytest.raises(DatosInvalidos) as error:
        service.validar_viajeros([datos_viajero(email="ana-sin-arroba")], hoy=HOY)

    assert (error.value.campos or {})["viajeros.0.email"] == "El formato no es válido."


def test_rf31_la_fecha_de_nacimiento_se_reubica_en_el_viajero() -> None:
    """RF-31 · SUP-43: la fecha futura se rechaza y el error queda en `viajeros.0`."""
    with pytest.raises(DatosInvalidos) as error:
        service.validar_viajeros([datos_viajero(fecha_nacimiento=HOY + timedelta(days=1))], hoy=HOY)

    assert "viajeros.0.fecha_nacimiento" in (error.value.campos or {})


def test_rf31_viajeros_validos_pasan() -> None:
    """RF-31: dos viajeros completos, con correos válidos, se aceptan."""
    service.validar_viajeros(
        [
            datos_viajero(),
            datos_viajero(numero_documento="1020304051", email="luis@example.com"),
        ],
        hoy=HOY,
    )


def test_rf32_cinco_activos_bloquean_el_sexto_y_cancelar_libera_cupo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-32 · HU-22, HU-24: 3 comprados y 2 reservados suman 5; el sexto se rechaza y
    cancelar uno vuelve a permitir agregar otro."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_limite")
    vuelo = crear_vuelo(db, salida=SALIDA)
    crear_compra(db, cliente.id, vuelo, cantidad=3)
    crear_reserva(db, cliente.id, vuelo, cantidad=2)

    assert service.tiquetes_activos_en_vuelo(db, cliente.id, vuelo.id) == 5
    with pytest.raises(service.LimiteDeTiquetes) as error:
        service.validar_limite_de_tiquetes(db, cliente.id, vuelo.id, 1)
    assert error.value.codigo == "limite_tiquetes"

    tiquetes = list(
        db.scalars(select(Tiquete).where(Tiquete.vuelo_id == vuelo.id).order_by(Tiquete.id))
    )
    tiquetes[0].estado = "cancelado"
    db.flush()

    service.validar_limite_de_tiquetes(db, cliente.id, vuelo.id, 1)
    assert service.tiquetes_activos_en_vuelo(db, cliente.id, vuelo.id) == 4

    tiquetes[1].estado = "vencido"
    db.flush()
    service.validar_limite_de_tiquetes(db, cliente.id, vuelo.id, 2)
    assert service.tiquetes_activos_en_vuelo(db, cliente.id, vuelo.id) == 3


def test_rf33_primera_agotada_se_rechaza_aunque_economica_tenga_sillas(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-33 · HU-24: con primera agotada no se puede elegir esa clase, aunque económica
    conserve disponibilidad."""
    cliente = crear_usuario(Rol.CLIENTE, nombre_usuario="cliente_primera")
    vuelo = crear_vuelo(db, salida=SALIDA, capacidad_primera=1)
    crear_compra(db, cliente.id, vuelo, clase="primera", cantidad=1)

    with pytest.raises(SillasInsuficientes) as error:
        service.validar_cupo(db, vuelo.id, "primera", 1)
    assert error.value.codigo == "clase_agotada"

    service.validar_cupo(db, vuelo.id, "economica", 1)


def test_rf34_documento_con_tiquete_activo_se_rechaza_sin_revelar_al_comprador(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-34 · HU-24: un documento con tiquete activo en el vuelo se rechaza con un mensaje
    que no revela quién hizo la otra compra; en otro vuelo sí se acepta."""
    cliente_uno = crear_usuario(
        Rol.CLIENTE, nombre_usuario="cliente_dup_uno", email="dup1@example.com"
    )
    cliente_dos = crear_usuario(
        Rol.CLIENTE, nombre_usuario="cliente_dup_dos", email="dup2@example.com"
    )
    vuelo_uno = crear_vuelo(db, salida=SALIDA)
    vuelo_dos = crear_vuelo(db, salida=SALIDA, origen="BOG", destino="MDE")
    crear_compra(db, cliente_uno.id, vuelo_uno, cantidad=1, numero_documento="123456")
    crear_compra(db, cliente_dos.id, vuelo_dos, cantidad=1, numero_documento="654321")

    with pytest.raises(service.ViajeroDuplicado) as error:
        service.validar_documentos_en_vuelo(
            db, vuelo_uno.id, [datos_viajero(numero_documento="123456")]
        )

    assert error.value.codigo == "viajero_duplicado"
    assert "cliente_dup_dos" not in error.value.mensaje.lower()
    assert "cliente_dup_dos" not in " ".join((error.value.campos or {}).values()).lower()

    # El mismo documento en otro vuelo no tiene un tiquete activo: se acepta.
    service.validar_documentos_en_vuelo(
        db, vuelo_dos.id, [datos_viajero(numero_documento="123456")]
    )

    # Al cancelar el tiquete, el documento queda libre en el primer vuelo.
    tiquete = db.scalar(
        select(Tiquete).where(
            Tiquete.vuelo_id == vuelo_uno.id,
            Tiquete.numero_documento == "123456",
        )
    )
    assert tiquete is not None
    tiquete.estado = "cancelado"
    db.flush()
    service.validar_documentos_en_vuelo(
        db, vuelo_uno.id, [datos_viajero(numero_documento="123456")]
    )

    # Dos documentos iguales en la misma solicitud también se rechazan.
    with pytest.raises(service.ViajeroDuplicado) as repetido:
        service.validar_documentos_en_vuelo(
            db,
            vuelo_dos.id,
            [
                datos_viajero(numero_documento="777777"),
                datos_viajero(numero_documento="777777"),
            ],
        )
    assert "viajeros.1.numero_documento" in (repetido.value.campos or {})


def test_rf35_un_menor_solo_no_puede_viajar(
    db: Session,
) -> None:
    """RF-35 · HU-24: una reserva con un único viajero de 16 años se rechaza."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    menor = datos_viajero(fecha_nacimiento=date(2009, 6, 2))  # cumple 18 al día siguiente

    with pytest.raises(service.MenorSinAdulto) as error:
        service.validar_menores(db, vuelo.id, [menor])

    assert error.value.codigo == "menor_sin_adulto"
    assert "viajeros.0.fecha_nacimiento" in (error.value.campos or {})


def test_rf35_un_menor_acompanado_por_un_adulto_puede_viajar(db: Session) -> None:
    """RF-35 · HU-24: un menor viaja si la transacción incluye un adulto en el mismo vuelo."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    service.validar_menores(
        db,
        vuelo.id,
        [
            datos_viajero(fecha_nacimiento=date(2009, 6, 2)),
            datos_viajero(numero_documento="1020304051", fecha_nacimiento=date(1990, 1, 1)),
        ],
    )


def test_rf35_quien_cumple_18_antes_del_vuelo_viaja_solo(db: Session) -> None:
    """RF-35 · HU-24: un viajero que cumple 18 años antes de la fecha del vuelo puede
    viajar solo, aunque al momento de comprar todavía sea menor."""
    vuelo = crear_vuelo(db, salida=SALIDA)
    service.validar_menores(
        db,
        vuelo.id,
        [datos_viajero(fecha_nacimiento=date(2009, 5, 31))],
    )
