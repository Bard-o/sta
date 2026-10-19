from fastapi.testclient import TestClient


def test_ruta_inexistente_usa_el_formato_unico(client: TestClient):
    respuesta = client.get("/api/v1/no-existe")
    assert respuesta.status_code == 404
    assert respuesta.json() == {
        "error": {"codigo": "no_encontrado", "mensaje": "El recurso no existe."}
    }


def test_validacion_devuelve_errores_por_campo(client: TestClient):
    respuesta = client.post("/api/v1/auth/login", json={"usuario": ""})
    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert error["campos"] == {
        "usuario": "Es demasiado corto.",
        "contrasena": "Este campo es obligatorio.",
    }


def test_health(client: TestClient):
    respuesta = client.get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "base_de_datos": "ok"}
