from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DatosInvalidos
from app.core.security import Rol
from app.modules.auditoria import service
from app.modules.auditoria.models import RegistroAuditoria

ACCIONES = [
    ("vuelo.crear", "vuelo"),
    ("vuelo.editar", "vuelo"),
    ("vuelo.cancelar", "vuelo"),
    ("promocion.crear", "promocion"),
    ("administrador.crear", "usuario"),
    ("administrador.desactivar", "usuario"),
    ("administrador.reactivar", "usuario"),
]


def test_registra_quien_que_entidad_valores_y_fecha_en_utc(db: Session, crear_usuario):
    # RF-26 / HU-15: editar el precio de un vuelo deja el valor anterior y el nuevo.
    usuario = crear_usuario(Rol.ADMIN)
    antes = {"precio_economica": 1386000, "salida": "2026-12-10T22:00:00Z"}
    despues = {"precio_economica": 1250000, "salida": "2026-12-10T22:00:00Z"}

    service.registrar(
        db,
        usuario_id=usuario.id,
        accion="vuelo.editar",
        entidad="vuelo",
        entidad_id=42,
        antes=antes,
        despues=despues,
    )

    registro = db.scalars(select(RegistroAuditoria)).one()
    assert registro.usuario_id == usuario.id
    assert registro.accion == "vuelo.editar"
    assert registro.entidad == "vuelo"
    assert registro.entidad_id == 42
    assert registro.antes == antes
    assert registro.despues == despues
    assert registro.creado_en.tzinfo is not None
    assert abs(registro.creado_en - datetime.now(UTC)) < timedelta(minutes=5)


@pytest.mark.parametrize(("accion", "entidad"), ACCIONES)
def test_acepta_las_acciones_del_contrato(accion, entidad, db: Session, crear_usuario):
    # RF-26: las siete acciones administrativas del contrato de la iteración 1.
    usuario = crear_usuario(Rol.ADMIN)

    service.registrar(
        db,
        usuario_id=usuario.id,
        accion=accion,
        entidad=entidad,
        entidad_id=1,
    )

    registro = db.scalars(select(RegistroAuditoria)).one()
    assert (registro.accion, registro.entidad) == (accion, entidad)


def test_rechaza_una_accion_fuera_del_contrato(db: Session, crear_usuario):
    # RF-26: solo se aceptan las acciones auditables del contrato.
    usuario = crear_usuario(Rol.ADMIN)

    with pytest.raises(DatosInvalidos) as exc:
        service.registrar(
            db,
            usuario_id=usuario.id,
            accion="vuelo.borrar",
            entidad="vuelo",
            entidad_id=1,
        )

    assert exc.value.codigo == "datos_invalidos"
    assert exc.value.campos == {"accion": "No es una acción auditable."}


def test_rechaza_una_entidad_fuera_del_contrato(db: Session, crear_usuario):
    # RF-26: la entidad auditada es vuelo, promocion o usuario.
    usuario = crear_usuario(Rol.ADMIN)

    with pytest.raises(DatosInvalidos) as exc:
        service.registrar(
            db,
            usuario_id=usuario.id,
            accion="vuelo.crear",
            entidad="reserva",
            entidad_id=1,
        )

    assert exc.value.codigo == "datos_invalidos"
    assert exc.value.campos == {"entidad": "No es una entidad auditable."}


def test_rollback_del_llamador_no_deja_el_registro(db: Session, crear_usuario):
    # RF-26 / RNF-17: registrar no hace commit; si el llamador revierte, no queda el registro.
    usuario = crear_usuario(Rol.ADMIN)

    service.registrar(
        db,
        usuario_id=usuario.id,
        accion="vuelo.crear",
        entidad="vuelo",
        entidad_id=1,
        despues={"codigo": "STA-00001"},
    )
    assert db.scalar(select(func.count()).select_from(RegistroAuditoria)) == 1

    db.rollback()

    assert db.scalar(select(func.count()).select_from(RegistroAuditoria)) == 0


def test_sin_antes_ni_despues_guarda_null_de_sql(db: Session, crear_usuario):
    # RF-26: crear o desactivar puede no tener valor anterior; la columna queda en NULL, no en
    # el JSON `null`, para que la consulta de HU-50 pueda filtrar con IS NULL.
    usuario = crear_usuario(Rol.ADMIN)

    service.registrar(
        db,
        usuario_id=usuario.id,
        accion="vuelo.crear",
        entidad="vuelo",
        entidad_id=1,
    )

    sin_valores = db.scalar(
        select(func.count())
        .select_from(RegistroAuditoria)
        .where(RegistroAuditoria.antes.is_(None), RegistroAuditoria.despues.is_(None))
    )
    assert sin_valores == 1


@pytest.mark.parametrize(
    "detalle",
    [
        {"contrasena": "Clave1234"},
        {"contraseña": "Clave1234"},
        {"contrasena_temporal": "Clave1234"},
        {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$hash"},
        {"datos": {"contrasena": "Clave1234"}},
        {"lista": [{"password": "Clave1234"}]},
    ],
)
@pytest.mark.parametrize("campo", ["antes", "despues"])
def test_rechaza_claves_de_contrasena(campo, detalle, db: Session, crear_usuario):
    # RF-26: ni en `antes` ni en `despues`, ni en objetos anidados, se auditan contraseñas.
    usuario = crear_usuario(Rol.ADMIN)

    with pytest.raises(DatosInvalidos) as exc:
        service.registrar(
            db,
            usuario_id=usuario.id,
            accion="administrador.crear",
            entidad="usuario",
            entidad_id=1,
            **{campo: detalle},
        )

    assert exc.value.codigo == "datos_invalidos"
    assert exc.value.campos == {campo: "No puede contener contraseñas."}


@pytest.mark.parametrize(
    "valor",
    [
        {"fecha": datetime.now(UTC)},
        {"precio": Decimal("10.5")},
        {"clases": {"economica"}},
        {"imagen": b"bytes"},
        {"objeto": object()},
        {"precio": float("nan")},
    ],
)
@pytest.mark.parametrize("campo", ["antes", "despues"])
def test_rechaza_valores_no_serializables(campo, valor, db: Session, crear_usuario):
    # RF-26: las fechas van como texto ISO 8601 y solo se aceptan valores serializables.
    usuario = crear_usuario(Rol.ADMIN)

    with pytest.raises(DatosInvalidos) as exc:
        service.registrar(
            db,
            usuario_id=usuario.id,
            accion="vuelo.editar",
            entidad="vuelo",
            entidad_id=1,
            **{campo: valor},
        )

    assert exc.value.codigo == "datos_invalidos"
    assert exc.value.campos == {
        campo: "Solo admite valores serializables en JSON (fechas en ISO 8601)."
    }


@pytest.mark.parametrize("campo", ["antes", "despues"])
def test_rechaza_un_detalle_que_no_es_objeto(campo, db: Session, crear_usuario):
    # RF-26: antes y despues son objetos JSON con los valores del cambio.
    usuario = crear_usuario(Rol.ADMIN)

    with pytest.raises(DatosInvalidos) as exc:
        service.registrar(
            db,
            usuario_id=usuario.id,
            accion="vuelo.editar",
            entidad="vuelo",
            entidad_id=1,
            **{campo: ["no", "es", "un", "objeto"]},
        )

    assert exc.value.codigo == "datos_invalidos"
    assert exc.value.campos == {campo: "Debe ser un objeto JSON."}


def test_permite_fechas_iso_y_claves_que_no_son_contrasena(db: Session, crear_usuario):
    # RF-26: una fecha ISO 8601 y una clave como clave_vuelo no son contraseñas.
    usuario = crear_usuario(Rol.ADMIN)
    despues = {"salida": "2026-12-10T22:00:00Z", "clave_vuelo": "STA-00001"}

    service.registrar(
        db,
        usuario_id=usuario.id,
        accion="vuelo.crear",
        entidad="vuelo",
        entidad_id=1,
        despues=despues,
    )

    registro = db.scalars(select(RegistroAuditoria)).one()
    assert registro.despues == despues
