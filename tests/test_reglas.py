"""Reglas de negocio (guía §4), contrastadas contra el informe publicado."""

from __future__ import annotations

import pytest
from jumpdia.normalizacion import a_pct, redondear_pct, texto_largo
from jumpdia.reglas import (
    estado_recomendacion,
    etiqueta_unidades,
    global_estudiante,
    logro_mostrado,
    logro_puntaje,
    promedio_eje,
    promedio_global,
    semaforo,
)


@pytest.mark.parametrize(
    "pct, esperado",
    [
        (100, "V"), (80, "V"), (81, "V"),
        (79, "A"), (73, "A"), (60, "A"),
        (59, "R"), (38, "R"), (0, "R"),
        # El color se decide sobre el % ya redondeado que ve el usuario:
        # un 79,6 se muestra como 80 y debe leerse verde.
        (79.6, "V"), (59.5, "A"),
        (None, "N"),
    ],
)
def test_semaforo(pct, esperado):
    assert semaforo(pct) == esperado


def test_logro_mostrado_no_cuenta_credito_parcial():
    """La P5 de 4° A se publica como 38 %, no como 50 %."""
    dist = {"RC": 38.46, "RPC": 23.08, "RI": 38.46}
    assert redondear_pct(logro_mostrado("desarrollo", dist)) == 38


def test_logro_puntaje_cuenta_medio_punto():
    """El promedio del eje sí puntúa la respuesta parcialmente correcta."""
    dist = {"RC": 38.46, "RPC": 23.08, "RI": 38.46}
    assert logro_puntaje("desarrollo", dist) == pytest.approx(50.0)


def test_logro_alternativas_toma_la_clave():
    dist = {"A": 3.85, "B": 7.69, "C": 7.69, "D": 80.77, "N": 0.0}
    assert logro_mostrado("alternativas", dist) == pytest.approx(80.77)
    assert logro_mostrado("alternativas", {**dist, "clave": "B"}) == pytest.approx(7.69)


def test_promedio_eje_reproduce_los_cinco_ejes(D_publicado):
    """Los 5 ejes del informe salen del promedio de puntajes con crédito parcial."""
    for i, eje in enumerate(D_publicado["ejes"]):
        puntajes = [
            logro_puntaje(q["tipo"], q["dist"])
            for q in D_publicado["questions"]
            if q["eje"] == eje
        ]
        assert promedio_eje(puntajes) == pytest.approx(D_publicado["ejeProm"][i], abs=0.05)


def test_promedio_global_es_ponderado_no_simple(D_publicado):
    ponderado = promedio_global(D_publicado["ejeProm"], D_publicado["ejeQC"])
    simple = round(sum(D_publicado["ejeProm"]) / 5)
    assert ponderado == D_publicado["promGlobal"] == 73
    assert simple == 72, "el promedio simple da otro número: la ponderación importa"


def test_global_estudiante_exacto_vs_aproximado():
    """Con puntaje crudo el global es exacto; sin él puede desviarse un punto.

    Caso real: Roldán Morales, 16 de 31 aciertos → 52 %. Ponderando los % por
    eje ya redondeados (53, 33, 75, 50, 33) da 51.
    """
    qc = [15, 3, 4, 6, 3]
    pcts = [53.0, 33.0, 75.0, 50.0, 33.0]
    assert global_estudiante(pcts, qc, puntaje_crudo=16) == 52
    assert global_estudiante(pcts, qc) == 51


def test_estado_recomendacion():
    assert estado_recomendacion([True, False]) == "remediar"
    assert estado_recomendacion([False, False]) == "esperado"
    assert estado_recomendacion([]) == "esperado"


def test_etiqueta_unidades():
    unidades = [
        {
            "tomo": "4.1",
            "u": "U2",
            "label": "Valor posicional, sumas y restas",
            "status": "res",
            "pct": 85,
        },
        {"tomo": "4.2", "u": "U3", "label": "Problemas", "status": "none", "pct": None},
    ]
    assert etiqueta_unidades(unidades) == (
        "4.1 · U2 Valor posicional, sumas y restas ✓ 85% · 4.2 · U3 Problemas ✗"
    )


@pytest.mark.parametrize(
    "valor, esperado",
    [("84,6 %", 84.6), ("84.6", 84.6), (0.846, 84.6), (84, 84), ("-", None), ("", None), (1, 100)],
)
def test_a_pct(valor, esperado):
    assert a_pct(valor) == pytest.approx(esperado) if esperado is not None else a_pct(valor) is None


def test_redondear_pct_es_comercial():
    """`round()` de Python usa redondeo bancario; el informe redondea hacia arriba."""
    assert redondear_pct(69.5) == 70
    assert redondear_pct(50.5) == 51 and round(50.5) == 50


def test_texto_largo_conserva_los_espacios_de_la_planilla():
    assert texto_largo("Uno.  Dos.\nTres. ") == "Uno.  Dos. Tres."
