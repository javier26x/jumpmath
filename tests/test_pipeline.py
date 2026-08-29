"""Prueba de extremo a extremo: archivos de origen → objeto `D`.

El criterio es exigente a propósito: partiendo de los cuatro archivos hay que
volver a obtener, campo por campo, el mismo `D` del informe 4° A publicado.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from jumpdia import Archivo, ErrorParseo, ErrorValidacion, ensamblar, inyectar_D, validar
from jumpdia.catalogo import UNIDADES_JUMP


def test_reconstruye_el_informe_publicado(D_reconstruido, D_publicado):
    assert D_reconstruido == D_publicado


@pytest.mark.parametrize(
    "clave",
    [
        "meta", "niveles", "ejes", "ejeProm", "promGlobal",
        "students", "questions", "coverage", "recs", "ejeQC",
    ],
)
def test_cada_clave_del_contrato(D_reconstruido, D_publicado, clave):
    """Falla por clave, para que el diagnóstico apunte a la sección exacta."""
    assert D_reconstruido[clave] == D_publicado[clave]


def test_los_avisos_son_solo_informativos(entrada):
    """La ingesta limpia avisa de dos cosas, y ninguna es un problema de datos.

    Que los Gráficos 1 y 2 no tengan capa de texto, y qué unidades quedaron
    sin control registrado. Cualquier otro aviso señala algo que revisar.
    """
    salida = ensamblar(entrada)
    sin_registro = [c for c in salida.D["coverage"] if c["status"] == "none"]

    graficos = [a for a in salida.avisos if "gráficos sin capa de texto" in a]
    pendientes = [a for a in salida.avisos if "no tiene resultados registrados" in a]

    assert len(graficos) == 1
    assert len(pendientes) == len(sin_registro)
    assert len(salida.avisos) == len(graficos) + len(pendientes), salida.avisos


def test_D_reconstruido_pasa_la_validacion(D_reconstruido):
    assert validar(D_reconstruido) == []


def test_niveles_vienen_del_pdf_no_de_cortes_de_porcentaje(D_reconstruido):
    """Un estudiante puede tener <60 % global y ser Nivel II (guía §4)."""
    bajo_60_en_nivel_2 = [
        s for s in D_reconstruido["students"] if s["g"] < 60 and s["lv"] == 2
    ]
    assert bajo_60_en_nivel_2, "el fixture debe contener este caso"
    assert D_reconstruido["niveles"] == {"I": 0, "II": 13, "III": 13}


def test_cobertura_sin_registro_no_es_cero(D_reconstruido):
    """`status:'none'` no significa "no trabajada" ni 0 % (guía §4)."""
    sin_registro = [c for c in D_reconstruido["coverage"] if c["status"] == "none"]
    assert sin_registro
    assert all(c["pct"] is None for c in sin_registro)


def test_cobertura_lista_las_catorce_unidades_en_orden(D_reconstruido):
    esperado = [(u.tomo, u.u, u.label) for u in UNIDADES_JUMP]
    obtenido = [(c["tomo"], c["u"], c["label"]) for c in D_reconstruido["coverage"]]
    assert obtenido == esperado


def test_recs_cubre_todo_indicador_descendido(D_reconstruido):
    descendidos = {q["q"] for q in D_reconstruido["questions"] if q["pct"] < 80}
    assert {r["q"] for r in D_reconstruido["recs"]} == descendidos
    assert len(descendidos) == 17


def test_recs_ordenadas_por_logro_ascendente(D_reconstruido):
    orden = [(r["pct"], r["q"]) for r in D_reconstruido["recs"]]
    assert orden == sorted(orden)


def test_indicadores_usan_la_redaccion_del_informe_oficial(D_reconstruido, D_publicado):
    """La guía exige la redacción textual del DIA, sin reescrituras."""
    assert [q["ind"] for q in D_reconstruido["questions"]] == [
        q["ind"] for q in D_publicado["questions"]
    ]


def test_inyeccion_en_la_plantilla_es_reversible(D_reconstruido):
    from tests.conftest import RAIZ

    plantilla = (RAIZ / "public" / "index.html").read_text(encoding="utf-8")
    html = inyectar_D(plantilla, D_reconstruido)
    inicio = html.index("const D=") + len("const D=")
    releido, _ = json.JSONDecoder().raw_decode(html, inicio)
    assert releido == D_reconstruido
    assert "</script>" not in html[inicio : inicio + 200_000].split("\n")[0]


def test_falta_un_archivo_obligatorio_falla_con_diagnostico(entrada):
    rota = dataclasses.replace(entrada, estudiantes=Archivo("estudiantes.xlsx", b"no soy xlsx"))
    with pytest.raises(ErrorParseo) as exc:
        ensamblar(rota)
    assert "resultados por estudiante" in str(exc.value) or "xlsx" in str(exc.value)


def test_modo_no_estricto_devuelve_los_problemas_como_avisos(entrada, monkeypatch):
    """Con `estricto=False` se puede previsualizar un informe incompleto."""
    from jumpdia import ensamblaje as mod

    monkeypatch.setattr(mod, "validar", lambda _D: ["problema de prueba"])
    salida = ensamblar(entrada, estricto=False)
    assert "problema de prueba" in salida.avisos
    with pytest.raises(ErrorValidacion):
        ensamblar(entrada, estricto=True)
