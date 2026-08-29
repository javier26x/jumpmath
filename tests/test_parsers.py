"""Comportamientos de los parsers que sólo se vieron con archivos reales.

Cada test de aquí corresponde a algo que un fixture inventado no habría
mostrado y que, sin tratar, produce un informe con números equivocados.
"""

from __future__ import annotations

import copy

import pytest
from jumpdia.catalogo import unidad_por_nombre
from jumpdia.parsers.dia_oficial import parsear_dia_oficial
from jumpdia.parsers.seguimiento import parsear_seguimiento

# --- El destacado en negrita marca la alternativa correcta ---------------


@pytest.fixture(scope="module")
def pdf_clave_no_maxima(tmp_path_factory, D_publicado):
    """PDF con un ítem cuya clave **no** es la alternativa más elegida.

    Es el caso real de la P7 de 4° A en Santa Rosa: la respuesta correcta la
    marcó el 9,68 % del curso y dos distractores empataron en 38,71 %. Quien
    resuelva el logro tomando el máximo publica un 39 % donde va un 10 %.
    """
    from tests.generar_fixtures import escribir_dia_pdf

    pregunta = copy.deepcopy(D_publicado["questions"][0])
    pregunta.update(
        q=7,
        tipo="alternativas",
        dist={"A": 38.71, "B": 9.68, "C": 38.71, "D": 6.45, "N": 6.45, "clave": "B"},
    )
    destino = tmp_path_factory.mktemp("dia") / "clave_no_maxima.pdf"
    escribir_dia_pdf(destino, questions=[pregunta], meta=D_publicado["meta"])
    return destino.read_bytes()


def test_la_clave_se_toma_del_destacado_no_del_maximo(pdf_clave_no_maxima):
    resultado = parsear_dia_oficial(pdf_clave_no_maxima, "clave_no_maxima.pdf")
    pregunta = resultado.questions[0]
    assert pregunta["dist"]["clave"] == "B"
    assert pregunta["pct"] == 10, "tomar el máximo daría 39 %"
    assert pregunta["sem"] == "R"


def test_la_clave_no_se_publica_en_D(D_reconstruido):
    """`dist` es la distribución de respuestas: no se le añaden claves (§3)."""
    for pregunta in D_reconstruido["questions"]:
        assert "clave" not in pregunta["dist"]


def test_el_pdf_da_los_metadatos_del_curso(D_reconstruido, D_publicado):
    assert D_reconstruido["meta"] == D_publicado["meta"]


# --- Cobertura JUMP: una hoja por evaluación -----------------------------


def test_la_fila_de_totales_no_cuenta_como_estudiante(entrada):
    """«Total por pregunta» cierra la nómina y tiene su misma forma.

    Contarla como un alumno más mete la suma de la columna en el promedio y
    desvía el logro de la unidad.
    """
    resultado = parsear_seguimiento(entrada.seguimiento.datos, entrada.seguimiento.nombre)
    registradas = [c for c in resultado.coverage if c["status"] == "res"]
    assert registradas
    assert all(0 < c["pct"] <= 100 for c in registradas)


def test_hoja_preparada_sin_aplicar_queda_sin_registro(entrada):
    """Una evaluación creada pero no rendida no es un 0 %: es "sin registro"."""
    resultado = parsear_seguimiento(entrada.seguimiento.datos, entrada.seguimiento.nombre)
    sin_registro = [c for c in resultado.coverage if c["status"] == "none"]
    assert sin_registro
    assert all(c["pct"] is None for c in sin_registro)
    assert any("no tiene resultados registrados" in a for a in resultado.avisos)


@pytest.mark.parametrize(
    "numero, etiqueta, esperado",
    [
        # El número no basta: la Unidad 1 es «Series» en el Tomo 4.1 y
        # «Figuras» en el 4.2. Decide el nombre.
        (1, "Series", "4.1/U1"),
        (1, "Figuras", "4.2/U1"),
        (2, "Valor posicional, sumas y restas", "4.1/U2"),
        (2, "Hallar el resto", "4.2/U2"),
        (6, "Unidades métricas y tiempo", "4.1/U6"),
        (6, "Área y volumen", "4.2/U6"),
        # Errata real en la planilla de un colegio.
        (6, "Undades métricas y tiempo", "4.1/U6"),
        (8, "Diagramas", "4.2/U8"),
    ],
)
def test_unidad_resuelta_por_nombre(numero, etiqueta, esperado):
    unidad = unidad_por_nombre(numero, etiqueta)
    assert unidad is not None and unidad.clave == esperado


def test_unidad_desconocida_no_se_inventa():
    assert unidad_por_nombre(9, "Cualquier cosa") is None
    assert unidad_por_nombre(1, "Un nombre que no se parece a nada") is None


# --- Niveles de logro ----------------------------------------------------


def test_los_niveles_salen_de_la_nomina_cuando_el_pdf_no_los_trae(D_reconstruido, entrada):
    """Los Gráficos 1 y 2 son imágenes sin capa de texto.

    Contar el nivel oficial de cada estudiante no es recalcularlo con cortes
    de porcentaje —lo que la guía prohíbe—: es agregar la misma clasificación
    de la Agencia que ya viene por estudiante en la nómina.
    """
    dia = parsear_dia_oficial(entrada.dia_oficial.datos, entrada.dia_oficial.nombre)
    assert dia.niveles == {}, "el PDF no publica el recuento en texto"

    conteo = {"I": 0, "II": 0, "III": 0}
    for alumno in D_reconstruido["students"]:
        conteo[("I", "II", "III")[alumno["lv"] - 1]] += 1
    assert D_reconstruido["niveles"] == conteo
