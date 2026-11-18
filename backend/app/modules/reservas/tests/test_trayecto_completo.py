"""Trayecto completo: ida y regreso en una sola reserva o compra (HU-26, RF-28, RF-40, SUP-14).

Un trayecto completo es una sola transacción con un solo código y dos tiquetes por viajero, uno
por tramo, cada uno con su clase y su silla. El regreso sale del destino de la ida,
estrictamente después de su llegada, y puede terminar en otra ciudad (RF-28). Si cualquier
tramo incumple una regla, no se crea ninguno de los dos (SUP-14, RNF-17).
"""

import io
import re
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import archivos
from app.core.db import AdjuntoEnCola, CorreoEnCola
from app.core.testing import CONTRASENA_TEST
from app.modules.monedero import service as monedero_service
from app.modules.monedero.models import Movimiento
from app.modules.monedero.tests.fabricas import crear_movimiento
from app.modules.reservas import service
from app.modules.reservas.models import Tiquete, Tramo, Transaccion
from app.modules.reservas.sillas import SillasInsuficientes
from app.modules.reservas.tests.apoyo import (
    AHORA,
    SALIDA,
    cliente_verificado,
    entrada,
    tiquetes_de,
    viajero,
)
from app.modules.vuelos.models import Vuelo
from app.modules.vuelos.tests.fabricas import crear_vuelo

# Precios de la historia: Pereira → Nueva York en primera y Nueva York → Cartagena en económica.
PRIMERA_IDA = 4_100_000
ECONOMICA_IDA = 2_000_000
PRIMERA_REGRESO = 5_000_000
ECONOMICA_REGRESO = 1_750_000
TOTAL_TRAYECTO = PRIMERA_IDA + ECONOMICA_REGRESO


def _vuelos(db: Session) -> tuple[Vuelo, Vuelo]:
    """Ida Pereira → Nueva York y regreso Nueva York → Cartagena, después de la llegada."""
    ida = crear_vuelo(
        db,
        origen="PEI",
        destino="JFK",
        tipo="internacional",
        salida=SALIDA,
        precio_primera=PRIMERA_IDA,
        precio_economica=ECONOMICA_IDA,
    )
    regreso = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=ida.llegada + timedelta(hours=2),
        precio_primera=PRIMERA_REGRESO,
        precio_economica=ECONOMICA_REGRESO,
    )
    return ida, regreso


def _cuenta(db: Session, modelo: type) -> int:
    return db.scalar(select(func.count()).select_from(modelo)) or 0


def _assert_regreso_invalido(error: service.RegresoInvalido) -> None:
    assert error.codigo == "regreso_invalido"
    assert error.status_code == 422
    assert "tramos.1.vuelo_id" in (error.campos or {})


# ---------- El trayecto completo (HU-26, RF-40, SUP-14) ----------


def test_hu26_el_trayecto_completo_comparte_el_codigo_y_suma_los_precios(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · RF-40 · SUP-14: Pereira → Nueva York en primera y Nueva York → Cartagena en

    económica suman sus precios en una sola reserva, con un solo código y dos tiquetes.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_trayecto")
    ida, regreso = _vuelos(db)
    datos = entrada(
        [ida, regreso],
        [viajero("1020306001", clases=("primera", "economica"), email="daniel@example.com")],
    )

    reserva = service.crear_reserva(db, cliente.id, datos, ahora=AHORA)

    assert reserva.tipo == "reserva"
    assert reserva.estado == "vigente"
    assert reserva.codigo is not None
    assert len(reserva.codigo) == 6

    viaje = service.viaje_de(db, reserva)
    assert [tramo.vuelo.id for tramo in viaje.tramos] == [ida.id, regreso.id]
    # RF-28: el regreso sale del destino de la ida y puede terminar en otra ciudad.
    assert viaje.tramos[1].vuelo.origen.codigo == viaje.tramos[0].vuelo.destino.codigo
    assert viaje.tramos[1].vuelo.destino.codigo == "CTG"
    assert viaje.total == TOTAL_TRAYECTO
    assert viaje.total_pendiente == TOTAL_TRAYECTO

    tiquetes = viaje.viajeros[0].tiquetes
    assert [(tiquete.tramo, tiquete.clase, tiquete.precio) for tiquete in tiquetes] == [
        (0, "primera", PRIMERA_IDA),
        (1, "economica", ECONOMICA_REGRESO),
    ]


def test_hu26_cada_viajero_recibe_un_tiquete_por_tramo_con_su_silla(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · SUP-14 · RF-41: dos viajeros reciben cuatro tiquetes, uno por tramo y viajero,

    con una silla distinta en cada vuelo.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_trayecto_sillas")
    ida, regreso = _vuelos(db)
    datos = entrada(
        [ida, regreso],
        [
            viajero("1020306101", clases=("economica", "economica"), email="uno@example.com"),
            viajero("1020306102", clases=("economica", "economica"), email="dos@example.com"),
        ],
    )

    reserva = service.crear_reserva(db, cliente.id, datos, ahora=AHORA)

    assert len(tiquetes_de(db, reserva)) == 4
    viaje = service.viaje_de(db, reserva)
    for viajero_viaje in viaje.viajeros:
        assert [tiquete.tramo for tiquete in viajero_viaje.tiquetes] == [0, 1]
        assert all(tiquete.silla for tiquete in viajero_viaje.tiquetes)

    sillas_por_vuelo: dict[int, set[int]] = {}
    for tiquete in tiquetes_de(db, reserva):
        sillas_por_vuelo.setdefault(tiquete.vuelo_id, set()).add(tiquete.numero_silla)
    assert set(sillas_por_vuelo) == {ida.id, regreso.id}
    assert all(len(sillas) == 2 for sillas in sillas_por_vuelo.values())
    assert all(silla > ida.capacidad_primera for silla in sillas_por_vuelo[ida.id])
    assert all(silla > regreso.capacidad_primera for silla in sillas_por_vuelo[regreso.id])


def test_hu26_la_clase_se_elige_por_viajero_y_por_tramo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · RF-33: cada viajero puede ir en una clase distinta en cada tramo; hay un tramo

    por vuelo y clase, y cada tiquete hereda la clase y el precio de su tramo.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_trayecto_clases")
    ida, regreso = _vuelos(db)
    datos = entrada(
        [ida, regreso],
        [
            viajero("1020306201", clases=("primera", "economica"), email="uno@example.com"),
            viajero("1020306202", clases=("economica", "primera"), email="dos@example.com"),
        ],
    )

    reserva = service.crear_reserva(db, cliente.id, datos, ahora=AHORA)

    tramos = list(db.scalars(select(Tramo).where(Tramo.transaccion_id == reserva.id)))
    assert len(tramos) == 4
    assert {(tramo.orden, tramo.clase) for tramo in tramos} == {
        (1, "primera"),
        (1, "economica"),
        (2, "primera"),
        (2, "economica"),
    }

    viaje = service.viaje_de(db, reserva)
    assert [(tiquete.clase, tiquete.precio) for tiquete in viaje.viajeros[0].tiquetes] == [
        ("primera", PRIMERA_IDA),
        ("economica", ECONOMICA_REGRESO),
    ]
    assert [(tiquete.clase, tiquete.precio) for tiquete in viaje.viajeros[1].tiquetes] == [
        ("economica", ECONOMICA_IDA),
        ("primera", PRIMERA_REGRESO),
    ]
    assert viaje.total == PRIMERA_IDA + ECONOMICA_IDA + PRIMERA_REGRESO + ECONOMICA_REGRESO

    capacidades = {0: ida.capacidad_primera, 1: regreso.capacidad_primera}
    for viajero_viaje in viaje.viajeros:
        for tiquete in viajero_viaje.tiquetes:
            if tiquete.clase == "primera":
                assert tiquete.numero_silla <= capacidades[tiquete.tramo]
            else:
                assert tiquete.numero_silla > capacidades[tiquete.tramo]


# ---------- RF-28: reglas del regreso ----------


def test_rf28_el_regreso_debe_salir_del_destino_de_la_ida(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-28 · HU-26: un regreso que sale del origen de la ida se rechaza."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_regreso_origen")
    ida, _ = _vuelos(db)
    regreso = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        tipo="nacional",
        salida=ida.llegada + timedelta(hours=2),
    )

    with pytest.raises(service.RegresoInvalido) as error:
        service.crear_reserva(
            db,
            cliente.id,
            entrada(
                [ida, regreso],
                [viajero("1020306301", clases=("economica", "economica"))],
            ),
            ahora=AHORA,
        )

    _assert_regreso_invalido(error.value)


def test_rf28_el_regreso_no_puede_salir_antes_de_la_llegada(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-28 · HU-26: un regreso que sale antes de la llegada de la ida se rechaza."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_regreso_antes")
    ida, _ = _vuelos(db)
    regreso = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=ida.llegada - timedelta(minutes=30),
    )

    with pytest.raises(service.RegresoInvalido) as error:
        service.crear_reserva(
            db,
            cliente.id,
            entrada(
                [ida, regreso],
                [viajero("1020306302", clases=("economica", "economica"))],
            ),
            ahora=AHORA,
        )

    _assert_regreso_invalido(error.value)


def test_rf28_el_regreso_no_puede_salir_en_el_mismo_instante_de_la_llegada(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-28 · HU-26 · HU-21: el regreso debe salir estrictamente después de la llegada; un

    regreso en el mismo instante del aterrizaje de la ida se rechaza.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_regreso_igual")
    ida, _ = _vuelos(db)
    regreso = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=ida.llegada,
    )

    with pytest.raises(service.RegresoInvalido) as error:
        service.crear_reserva(
            db,
            cliente.id,
            entrada(
                [ida, regreso],
                [viajero("1020306303", clases=("economica", "economica"))],
            ),
            ahora=AHORA,
        )

    _assert_regreso_invalido(error.value)


def test_rf28_el_regreso_no_puede_ser_el_mismo_vuelo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """RF-28 · HU-26: el regreso es otro vuelo, nunca el mismo de la ida."""
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_regreso_mismo")
    ida, _ = _vuelos(db)

    with pytest.raises(service.RegresoInvalido) as error:
        service.crear_reserva(
            db,
            cliente.id,
            entrada([ida, ida], [viajero("1020306304", clases=("economica", "economica"))]),
            ahora=AHORA,
        )

    _assert_regreso_invalido(error.value)


# ---------- Si un tramo falla, no se crea ninguno (HU-26, RNF-17) ----------


@pytest.mark.parametrize(
    "crear",
    [service.crear_reserva, service.crear_compra],
    ids=["reserva", "compra"],
)
@pytest.mark.parametrize(
    ("regla", "codigo"),
    [
        ("cupo", "clase_agotada"),
        ("limite", "limite_tiquetes"),
        ("documento", "viajero_duplicado"),
        ("menor", "menor_sin_adulto"),
    ],
)
def test_hu26_si_un_tramo_incumple_una_regla_no_se_crea_ninguno_de_los_dos(
    db: Session,
    crear_usuario: Callable[..., Any],
    crear: Callable[..., Any],
    regla: str,
    codigo: str,
) -> None:
    """HU-26 · RNF-17: si el segundo tramo incumple cupo, límite de 5, documento duplicado o

    menores, no se crea ni la transacción ni ningún tiquete de los dos tramos.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_tramo_invalido")
    ida, regreso = _vuelos(db)
    nuevo = viajero("1020306401", clases=("economica", "economica"), email="nuevo@example.com")
    esperado: type[Exception]

    if regla == "cupo":
        # El regreso queda sin sillas en económica; la ida sí tiene.
        regreso.capacidad_economica = 1
        db.flush()
        otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_tramo_lleno")
        service.crear_compra(
            db,
            otro.id,
            entrada([regreso], [viajero("1020306402", email="otro@example.com")]),
            ahora=AHORA,
        )
        esperado = SillasInsuficientes
    elif regla == "limite":
        # El cliente ya tiene 5 tiquetes activos en el regreso, ninguno en la ida.
        cinco = [
            viajero(f"10203065{indice:02d}", email=f"cinco{indice}@example.com")
            for indice in range(5)
        ]
        service.crear_reserva(db, cliente.id, entrada([regreso], cinco), ahora=AHORA)
        esperado = service.LimiteDeTiquetes
    elif regla == "documento":
        # Otro cliente ya tiene ese documento en el regreso, no en la ida.
        otro = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_tramo_dueno")
        service.crear_compra(
            db,
            otro.id,
            entrada([regreso], [viajero("1020306401", email="otro@example.com")]),
            ahora=AHORA,
        )
        esperado = service.ViajeroDuplicado
    else:
        nuevo = viajero(
            "1020306401",
            clases=("economica", "economica"),
            fecha_nacimiento=date(2015, 1, 1),
            email="menor@example.com",
        )
        esperado = service.MenorSinAdulto

    antes = (_cuenta(db, Transaccion), _cuenta(db, Tiquete))
    with pytest.raises(esperado) as error:
        crear(db, cliente.id, entrada([ida, regreso], [nuevo]), ahora=AHORA)

    assert error.value.codigo == codigo
    assert (_cuenta(db, Transaccion), _cuenta(db, Tiquete)) == antes


# ---------- Vencimientos con dos tramos (HU-26, RF-36, SUP-15) ----------


def test_hu26_la_reserva_vence_con_el_limite_mas_proximo_de_sus_dos_vuelos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · RF-36: con dos vuelos, la reserva vence en min(24 h, límite de venta del tramo

    más próximo), que en la práctica es el de la ida.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_trayecto_vence")
    salida_ida = AHORA + timedelta(hours=10)
    ida = crear_vuelo(
        db,
        origen="PEI",
        destino="JFK",
        tipo="internacional",
        salida=salida_ida,
    )
    regreso = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=AHORA + timedelta(days=5),
    )
    datos = entrada(
        [ida, regreso],
        [viajero("1020306601", clases=("economica", "economica"))],
    )

    reserva = service.crear_reserva(db, cliente.id, datos, ahora=AHORA)

    assert reserva.vence_en == salida_ida - timedelta(hours=3)
    assert service.viaje_de(db, reserva).vence_en == reserva.vence_en


def test_hu26_el_bloqueo_de_la_compra_vence_con_el_limite_mas_proximo(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · SUP-15: con dos vuelos, el bloqueo de la compra vence en min(15 min, límite de

    venta del tramo más próximo).
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_trayecto_bloqueo")
    salida_ida = AHORA + timedelta(hours=3, minutes=10)
    ida = crear_vuelo(
        db,
        origen="PEI",
        destino="JFK",
        tipo="internacional",
        salida=salida_ida,
    )
    regreso = crear_vuelo(
        db,
        origen="JFK",
        destino="CTG",
        tipo="internacional",
        salida=AHORA + timedelta(hours=7),
    )
    datos = entrada(
        [ida, regreso],
        [viajero("1020306602", clases=("economica", "economica"))],
    )

    compra = service.crear_compra(db, cliente.id, datos, ahora=AHORA)

    assert compra.bloqueo_hasta == salida_ida - timedelta(hours=3)
    assert service.viaje_de(db, compra).vence_en == compra.bloqueo_hasta


# ---------- La compra de un trayecto completo (HU-26, HU-25) ----------


def test_hu26_la_compra_bloquea_los_dos_tramos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · SUP-14 · SUP-15: la compra de un trayecto completo bloquea un tiquete por

    tramo y su total suma los precios congelados de ambos vuelos.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="cliente_trayecto_compra")
    ida, regreso = _vuelos(db)
    datos = entrada(
        [ida, regreso],
        [viajero("1020306701", clases=("primera", "economica"), email="daniel@example.com")],
    )

    compra = service.crear_compra(db, cliente.id, datos, ahora=AHORA)

    assert compra.estado == "pendiente"
    assert compra.codigo is not None
    assert compra.bloqueo_hasta == AHORA + timedelta(minutes=15)
    tiquetes = tiquetes_de(db, compra)
    assert len(tiquetes) == 2
    assert all(tiquete.estado == "bloqueado" for tiquete in tiquetes)

    viaje = service.viaje_de(db, compra)
    assert len(viaje.tramos) == 2
    assert viaje.total == TOTAL_TRAYECTO
    assert viaje.total_pendiente == TOTAL_TRAYECTO


def test_hu26_confirmar_cobra_el_total_y_el_correo_y_el_comprobante_muestran_los_dos_tramos(
    db: Session, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · HU-25 · RF-39: al confirmar se cobra el total de los dos tramos y el correo del

    viajero y el comprobante en PDF muestran ambos vuelos bajo el mismo código.
    """
    cliente = cliente_verificado(
        db,
        crear_usuario,
        nombre_usuario="cliente_trayecto_paga",
        email="comprador.trayecto@example.com",
    )
    ida, regreso = _vuelos(db)
    crear_movimiento(db, cliente.id, valor=6_000_000, saldo_resultante=6_000_000)
    datos = entrada(
        [ida, regreso],
        [viajero("1020306801", clases=("primera", "economica"), email="viajero@example.com")],
    )
    compra = service.crear_compra(db, cliente.id, datos, ahora=AHORA)

    service.confirmar_compra(db, cliente.id, compra.id, ahora=AHORA)

    assert compra.estado == "activa"
    assert all(tiquete.estado == "comprado" for tiquete in tiquetes_de(db, compra))
    assert monedero_service.saldo_de(db, cliente.id) == 6_000_000 - TOTAL_TRAYECTO
    debito = db.scalars(
        select(Movimiento)
        .where(Movimiento.cliente_id == cliente.id, Movimiento.tipo == "compra")
        .order_by(Movimiento.id)
    ).one()
    assert debito.valor == -TOTAL_TRAYECTO
    assert debito.referencia == compra.codigo

    correos = list(db.scalars(select(CorreoEnCola).order_by(CorreoEnCola.id)))
    del_viajero = next(correo for correo in correos if correo.destinatario == "viajero@example.com")
    assert ida.codigo in del_viajero.texto
    assert regreso.codigo in del_viajero.texto

    comprobante = next(
        correo for correo in correos if correo.destinatario == "comprador.trayecto@example.com"
    )
    adjunto = db.scalars(
        select(AdjuntoEnCola).where(AdjuntoEnCola.correo_id == comprobante.id)
    ).one()
    texto = _texto_del_pdf(archivos.leer(adjunto.clave))
    for dato in (ida.codigo, regreso.codigo, "Pereira", "Nueva York", "Cartagena"):
        assert dato in texto


def _texto_del_pdf(contenido: bytes) -> str:
    """Texto del PDF con los espacios normalizados, para comparar celdas y líneas."""
    lector = PdfReader(io.BytesIO(contenido))
    return re.sub(r"\s+", " ", " ".join(pagina.extract_text() or "" for pagina in lector.pages))


# ---------- La API del trayecto completo (contrato de HU-26) ----------


def _login(client: TestClient, usuario: object) -> None:
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario.nombre_usuario, "contrasena": CONTRASENA_TEST},
    )
    assert respuesta.status_code == 200


def _cuerpo(ida: Vuelo, regreso: Vuelo, clases: tuple[str, str]) -> dict[str, object]:
    return entrada(
        [ida, regreso],
        [viajero("1020306901", clases=clases, email="daniel@example.com")],
    ).model_dump(mode="json")


def test_hu26_post_reservas_acepta_dos_tramos(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26: `POST /reservas` con dos tramos responde 201 con los dos vuelos y un tiquete por

    tramo, cada uno con su clase y su silla.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_trayecto_reserva")
    ida, regreso = _vuelos(db)
    _login(client, cliente)

    respuesta = client.post(
        "/api/v1/reservas", json=_cuerpo(ida, regreso, ("primera", "economica"))
    )

    assert respuesta.status_code == 201
    reserva = respuesta.json()
    assert reserva["tipo"] == "reserva"
    assert reserva["estado"] == "vigente"
    assert reserva["total"] == TOTAL_TRAYECTO
    assert [tramo["vuelo"]["id"] for tramo in reserva["tramos"]] == [ida.id, regreso.id]
    tiquetes = reserva["viajeros"][0]["tiquetes"]
    assert [(tiquete["tramo"], tiquete["clase"]) for tiquete in tiquetes] == [
        (0, "primera"),
        (1, "economica"),
    ]
    assert all(tiquete["silla"] for tiquete in tiquetes)


def test_hu26_post_compras_crea_y_confirma_dos_tramos(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26: `POST /compras` con dos tramos bloquea dos tiquetes y confirmar los cobra y los

    emite con el mismo código.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_trayecto_compra")
    crear_movimiento(db, cliente.id, valor=6_000_000, saldo_resultante=6_000_000)
    ida, regreso = _vuelos(db)
    _login(client, cliente)

    creada = client.post("/api/v1/compras", json=_cuerpo(ida, regreso, ("primera", "economica")))

    assert creada.status_code == 201
    compra = creada.json()
    assert compra["tipo"] == "compra"
    assert compra["estado"] == "pendiente"
    assert len(compra["tramos"]) == 2
    assert [tiquete["estado"] for tiquete in compra["viajeros"][0]["tiquetes"]] == [
        "bloqueado",
        "bloqueado",
    ]

    confirmada = client.post(f"/api/v1/compras/{compra['id']}/confirmar")

    assert confirmada.status_code == 200
    pagada = confirmada.json()
    assert pagada["estado"] == "activa"
    assert pagada["codigo"] == compra["codigo"]
    assert len(pagada["tramos"]) == 2
    assert [tiquete["estado"] for tiquete in pagada["viajeros"][0]["tiquetes"]] == [
        "comprado",
        "comprado",
    ]
    assert monedero_service.saldo_de(db, cliente.id) == 6_000_000 - TOTAL_TRAYECTO


def test_hu26_el_regreso_invalido_responde_el_formato_unico(
    db: Session, client: TestClient, crear_usuario: Callable[..., Any]
) -> None:
    """HU-26 · RF-28: un regreso inválido responde 422 `regreso_invalido` en el formato único,

    con el campo exacto del tramo y el destino de la ida en el mensaje.
    """
    cliente = cliente_verificado(db, crear_usuario, nombre_usuario="api_trayecto_invalido")
    ida, _ = _vuelos(db)
    regreso = crear_vuelo(
        db,
        origen="PEI",
        destino="BOG",
        tipo="nacional",
        salida=ida.llegada + timedelta(hours=2),
    )
    _login(client, cliente)

    respuesta = client.post(
        "/api/v1/reservas", json=_cuerpo(ida, regreso, ("economica", "economica"))
    )

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "regreso_invalido"
    assert "Nueva York" in error["mensaje"]
    assert error["campos"]["tramos.1.vuelo_id"] == (
        "Elige un regreso que salga después de tu llegada."
    )
    assert _cuenta(db, Transaccion) == 0
