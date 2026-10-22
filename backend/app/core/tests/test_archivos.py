"""Almacenamiento de archivos por clave (issue #6; imagen de perfil: HU-01/RF-03, HU-07/RF-08)."""

from pathlib import Path

import pytest

from app.core import archivos
from app.core.config import Settings
from app.core.errors import NoEncontrado


def test_guardar_y_leer_devuelve_los_mismos_bytes() -> None:
    """Issue #6 criterio 2, HU-01/RF-03: la imagen de perfil se guarda y se lee por clave."""
    contenido = bytes(range(256)) * 4
    archivos.guardar("perfiles/12", contenido)
    assert archivos.leer("perfiles/12") == contenido


def test_guardar_crea_la_raiz_y_las_carpetas_intermedias(archivos_dir: Path) -> None:
    """Issue #6 criterio 2: guardar no exige preparar el directorio antes."""
    assert not archivos_dir.exists()
    archivos.guardar("a/b/c", b"x")
    assert (archivos_dir / "a" / "b" / "c").read_bytes() == b"x"


def test_guardar_reemplaza_el_archivo_anterior(archivos_dir: Path) -> None:
    """Issue #6 criterio 2, HU-07/RF-08: cambiar la imagen de perfil reemplaza la anterior."""
    archivos.guardar("perfiles/12", b"A")
    archivos.guardar("perfiles/12", b"B")
    assert archivos.leer("perfiles/12") == b"B"
    assert [p.name for p in (archivos_dir / "perfiles").iterdir()] == ["12"]


def test_si_falla_el_reemplazo_se_conserva_el_archivo_anterior(
    archivos_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #6 criterio 2, HU-07/RF-08: un fallo al guardar no deja la imagen a medias."""
    archivos.guardar("perfiles/12", b"A")

    def falla(*_args: object, **_kwargs: object) -> None:
        raise OSError("disco lleno")

    with monkeypatch.context() as parche:
        parche.setattr("app.core.archivos.os.replace", falla)
        with pytest.raises(OSError):
            archivos.guardar("perfiles/12", b"B")

    assert archivos.leer("perfiles/12") == b"A"
    assert list((archivos_dir / "perfiles").glob(".*.tmp")) == []


def test_leer_una_clave_sin_archivo_lanza_no_encontrado() -> None:
    """Issue #6 criterio 2: leer algo que no existe es un 404 no_encontrado."""
    with pytest.raises(NoEncontrado) as error:
        archivos.leer("perfiles/99")
    assert error.value.status_code == 404
    assert error.value.codigo == "no_encontrado"


def test_borrar_elimina_el_archivo() -> None:
    """Issue #6 criterio 2: borrar quita el archivo."""
    archivos.guardar("perfiles/12", b"A")
    assert archivos.borrar("perfiles/12") is True
    with pytest.raises(NoEncontrado):
        archivos.leer("perfiles/12")


def test_borrar_una_clave_sin_archivo_devuelve_false() -> None:
    """Issue #6 criterio 2: borrar es idempotente."""
    assert archivos.borrar("perfiles/99") is False


@pytest.mark.parametrize("clave", ["a", "perfiles/12", "perfiles/usuario_12-v3", "a/b/c/d"])
def test_clave_valida(clave: str) -> None:
    """Issue #6 criterio 2: las claves con el formato documentado funcionan de ida y vuelta."""
    archivos.guardar(clave, b"ok")
    assert archivos.leer(clave) == b"ok"
    assert archivos.borrar(clave) is True


@pytest.mark.parametrize("operacion", ["guardar", "leer", "borrar"])
@pytest.mark.parametrize(
    "clave",
    [
        "",
        "../fuera",
        "perfiles/../../fuera",
        "/etc/passwd",
        "perfiles//12",
        "perfiles/",
        ".oculto",
        "perfiles/..",
        "a\\b",
        "a\x00b",
        "Perfiles/12",
        "perfiles/12.png",
        "-x",
        "a/b/c/d/e",
        "x" * 65,
    ],
)
def test_clave_invalida_se_rechaza_sin_tocar_el_disco(
    archivos_dir: Path, clave: str, operacion: str
) -> None:
    """Issue #6 criterio 2: ninguna clave puede apuntar fuera de la raíz ni a rutas arbitrarias."""
    with pytest.raises(ValueError, match="Clave de archivo inválida"):
        if operacion == "guardar":
            archivos.guardar(clave, b"x")
        elif operacion == "leer":
            archivos.leer(clave)
        else:
            archivos.borrar(clave)
    assert not (archivos_dir.parent / "fuera").exists()
    assert not archivos_dir.exists()


def test_un_enlace_simbolico_no_permite_salir_de_la_raiz(archivos_dir: Path) -> None:
    """Issue #6 criterio 2: un enlace simbólico dentro de la raíz no deja escribir afuera."""
    afuera = archivos_dir.parent / "afuera"
    afuera.mkdir()
    archivos_dir.mkdir()
    (archivos_dir / "perfiles").symlink_to(afuera, target_is_directory=True)

    with pytest.raises(ValueError, match="Clave de archivo inválida"):
        archivos.guardar("perfiles/12", b"x")
    with pytest.raises(ValueError, match="Clave de archivo inválida"):
        archivos.leer("perfiles/12")
    assert list(afuera.iterdir()) == []


def test_los_tests_usan_un_directorio_temporal(archivos_dir: Path, tmp_path: Path) -> None:
    """Issue #6 criterio 3: los tests escriben en un tmp_path, no en el volumen real."""
    archivos.guardar("perfiles/12", b"x")
    assert archivos_dir.is_relative_to(tmp_path)
    assert archivos_dir != Path("/data/archivos")
    assert (archivos_dir / "perfiles" / "12").exists()


def test_el_directorio_por_defecto_esta_fuera_del_codigo_montado() -> None:
    """Issue #6 criterio 1: por defecto los archivos van a /data/archivos, fuera de /app.

    /app es el código montado desde el anfitrión; /data/archivos es el volumen con nombre
    `archivos`. Que el volumen sobreviva a `down` y a reconstruir la imagen se comprueba a
    mano (ver la descripción del PR).
    """
    por_defecto = Settings.model_fields["archivos_dir"].default
    assert por_defecto == Path("/data/archivos")
    assert not por_defecto.is_relative_to(Path("/app"))
