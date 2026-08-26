"""Configuración común de los tests."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"
sys.path.insert(0, str(RAIZ / "functions"))


@pytest.fixture(scope="session")
def D_publicado() -> dict:
    """El objeto `D` del informe 4° A publicado: referencia dorada."""
    return json.loads((FIXTURES / "D_4A_bulnes.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def entrada():
    """Los cuatro archivos de origen sintéticos del curso 4° A."""
    from jumpdia import Archivo, Entrada

    def a(nombre: str) -> Archivo:
        return Archivo(nombre, (FIXTURES / nombre).read_bytes())

    return Entrada(
        dia_oficial=a("dia_oficial_4A.pdf"),
        estudiantes=a("estudiantes_4A.xlsx"),
        recomendaciones=a("recomendaciones_4B.xlsx"),
        seguimiento=a("seguimiento_jump_4A.xlsx"),
    )


@pytest.fixture(scope="session")
def D_reconstruido(entrada) -> dict:
    """`D` producido por el pipeline a partir de esos archivos."""
    from jumpdia import ensamblar

    return ensamblar(entrada).D
