"""Catálogo de ciudades (RF-12, SUP-32)."""

from sqlalchemy.orm import Session

from app.modules.vuelos import service

CAPITALES = {
    "LET",
    "MDE",
    "AUC",
    "BAQ",
    "CTG",
    "GUS",
    "MZL",
    "FLA",
    "EYP",
    "PPN",
    "VUP",
    "MTR",
    "BOG",
    "UIB",
    "RCH",
    "NVA",
    "SMR",
    "VVC",
    "PSO",
    "CUC",
    "VGZ",
    "AXM",
    "PEI",
    "ADZ",
    "BGA",
    "CZU",
    "IBE",
    "CLO",
    "MVP",
    "PCR",
    "PDA",
    "SJE",
}
INTERNACIONALES = {"MAD", "LHR", "JFK", "EZE", "MIA"}
HABILITADAS = {"PEI", "BOG", "MDE", "CLO", "CTG"}


def test_catalogo_tiene_las_32_capitales_y_los_5_destinos(db: Session):
    """HU-13: el catálogo son las 32 capitales departamentales y cinco destinos (RF-12)."""
    ciudades = service.listar_ciudades(db)

    assert len(ciudades) == 37
    assert {ciudad.codigo for ciudad in ciudades if ciudad.tipo == "nacional"} == CAPITALES
    assert {ciudad.codigo for ciudad in ciudades if ciudad.tipo == "internacional"} == (
        INTERNACIONALES
    )


def test_todas_las_ciudades_colombianas_usan_america_bogota(db: Session):
    """SUP-32: las ciudades nacionales comparten America/Bogota, sin horario de verano."""
    colombianas = [ciudad for ciudad in service.listar_ciudades(db) if ciudad.pais == "Colombia"]

    assert len(colombianas) == 32
    assert {ciudad.zona_horaria for ciudad in colombianas} == {"America/Bogota"}


def test_solo_las_cinco_ciudades_habilitadas_tienen_rutas_internacionales(db: Session):
    """RF-14: Pereira, Bogotá, Medellín, Cali y Cartagena son las puertas internacionales."""
    habilitadas = {
        ciudad.codigo for ciudad in service.listar_ciudades(db) if ciudad.habilitada_internacional
    }

    assert habilitadas == HABILITADAS


def test_zonas_horarias_de_los_destinos_internacionales(db: Session):
    """RF-12 · RF-15: cada destino internacional tiene su zona IANA con horario de verano."""
    zonas = {ciudad.codigo: ciudad.zona_horaria for ciudad in service.listar_ciudades(db)}

    assert zonas["MAD"] == "Europe/Madrid"
    assert zonas["LHR"] == "Europe/London"
    assert zonas["JFK"] == "America/New_York"
    assert zonas["EZE"] == "America/Argentina/Buenos_Aires"
    assert zonas["MIA"] == "America/New_York"


def test_todas_las_ciudades_tienen_imagen_del_banco(db: Session):
    """RF-12 · SUP-30: la imagen se sirve desde /imagenes/ciudades/<CODIGO>.jpg."""
    for ciudad in service.listar_ciudades(db):
        assert ciudad.imagen_url == f"/imagenes/ciudades/{ciudad.codigo}.jpg"


def test_mocoa_usa_el_codigo_de_villagarzon(db: Session):
    """RF-12: Mocoa no tiene aeropuerto propio; se usa VGZ, el de Villagarzón."""
    mocoa = service.obtener_ciudad(db, "VGZ")

    assert mocoa is not None
    assert mocoa.nombre == "Mocoa"
