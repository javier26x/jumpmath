"""Comprobaciones de la capa de Cloud Functions.

No levantan el emulador: verifican que el módulo carga, que declara las
funciones esperadas y que las validaciones de entrada rechazan lo que deben.
Así un error de dedo en `main.py` se ve en CI y no en el despliegue.
"""

from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture(scope="module")
def main(monkeypatch_module):
    """Carga `functions/main.py` fuera del runtime de Firebase.

    En producción el CLI de Firebase inyecta `FIREBASE_CONFIG` y las
    credenciales de servicio; aquí se simulan las dos cosas, porque el
    decorador de Storage exige conocer el bucket en tiempo de importación.
    """
    import json

    import firebase_admin

    monkeypatch_module.setenv(
        "FIREBASE_CONFIG",
        json.dumps({"projectId": "jumpmath-dia", "storageBucket": "jumpmath-dia.appspot.com"}),
    )
    monkeypatch_module.setenv("GCLOUD_PROJECT", "jumpmath-dia")
    monkeypatch_module.setattr(firebase_admin, "initialize_app", lambda *_a, **_k: None)
    sys.modules.pop("main", None)
    import main as modulo

    return modulo


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_el_modulo_carga_y_declara_las_funciones(main):
    for nombre in ("registrar_subida", "generar_informe", "informe", "obtener_informe"):
        assert hasattr(main, nombre), f"falta la función {nombre}"


def test_ranuras_coinciden_con_la_guia(main):
    assert main.RANURAS == {
        "dia_oficial": True,
        "estudiantes": True,
        "recomendaciones": True,
        "seguimiento": True,
        "plan_anual": False,
    }


@pytest.mark.parametrize("valido", ["1886-4a", "12345-8h", "100-1a"])
def test_curso_id_valido(main, valido):
    assert main._exigir_curso_id({"cursoId": valido}) == valido


@pytest.mark.parametrize(
    "invalido",
    ["", "1886", "4a", "1886-4", "1886-4z", "../../etc/passwd", "1886-4a/../otro", "abcd-4a"],
)
def test_curso_id_invalido_es_rechazado(main, invalido):
    """El id se usa para armar rutas de Storage: no puede admitir travesía."""
    from firebase_functions import https_fn

    with pytest.raises(https_fn.HttpsError):
        main._exigir_curso_id({"cursoId": invalido})


def test_sin_sesion_no_hay_ingesta(main):
    from firebase_functions import https_fn

    peticion = types.SimpleNamespace(auth=None, data={})
    with pytest.raises(https_fn.HttpsError):
        main._exigir_sesion(peticion)


def test_ruta_de_storage_queda_bajo_el_uid(main):
    assert main._ruta("uid123", "1886-4a", "dia_oficial") == "cursos/uid123/1886-4a/dia_oficial"
