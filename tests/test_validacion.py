"""El validador debe atrapar cada violación del contrato de datos."""

from __future__ import annotations

import copy

import pytest
from jumpdia import validar


@pytest.fixture
def D(D_publicado):
    return copy.deepcopy(D_publicado)


def _un_problema(D, fragmento):
    problemas = validar(D)
    assert any(fragmento in p for p in problemas), f"no se detectó «{fragmento}»: {problemas}"


def test_D_valido_no_reporta_nada(D):
    assert validar(D) == []


def test_detecta_claves_faltantes(D):
    del D["recs"]
    _un_problema(D, "faltan claves obligatorias")


def test_detecta_meta_n_inconsistente(D):
    D["meta"]["n"] = 25
    _un_problema(D, "no coincide con 26 estudiantes")


def test_detecta_promedio_global_no_ponderado(D):
    D["promGlobal"] = round(sum(D["ejeProm"]) / 5)  # promedio simple
    _un_problema(D, "no es el ponderado por N° de preguntas")


def test_detecta_semaforo_inconsistente(D):
    D["questions"][0]["sem"] = "R"  # está en 100 %
    _un_problema(D, "no corresponde a 100%")


def test_detecta_nivel_invalido(D):
    D["students"][0]["lv"] = 4
    _un_problema(D, "no es un nivel DIA")


def test_detecta_niveles_que_no_suman_la_nomina(D):
    D["niveles"]["II"] = 12
    _un_problema(D, "suma 25 estudiantes")


def test_detecta_cobertura_none_con_pct(D):
    sin_registro = next(c for c in D["coverage"] if c["status"] == "none")
    sin_registro["pct"] = 0
    _un_problema(D, "no debe traer pct")


def test_detecta_cobertura_res_sin_pct(D):
    registrada = next(c for c in D["coverage"] if c["status"] == "res")
    registrada["pct"] = None
    _un_problema(D, "exige un pct válido")


def test_detecta_indicador_descendido_sin_recomendacion(D):
    D["recs"].pop()
    _un_problema(D, "sin recomendación")


def test_detecta_recs_desordenadas(D):
    D["recs"].reverse()
    _un_problema(D, "no está ordenado")


def test_detecta_estado_remediar_sin_unidad_trabajada(D):
    esperado = next(r for r in D["recs"] if r["estado"] == "esperado")
    esperado["estado"] = "remediar"
    _un_problema(D, "no concuerda con units")


def test_detecta_estudiante_duplicado(D):
    D["students"].append(D["students"][0])
    D["meta"]["n"] = 27
    _un_problema(D, "estudiante duplicado")


def test_detecta_eje_qc_incoherente(D):
    D["ejeQC"] = [1, 1, 1, 1, 1]
    _un_problema(D, "preguntas con eje asignado")
