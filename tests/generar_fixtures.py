"""Genera archivos de entrada sintéticos que reproducen el informe 4° A.

Los archivos reales del colegio no están en el repositorio (traen datos
personales de estudiantes). Estos fixtures replican su **estructura** a partir
del `D` publicado, de modo que los tests puedan recorrer el pipeline completo
—PDF y planillas incluidos— y comprobar que se vuelve a obtener ese mismo `D`.

Uso:  python tests/generar_fixtures.py
"""

from __future__ import annotations

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "functions"))

from jumpdia.catalogo import EJE_CLAVES, EJES  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures"
D = json.loads((FIXTURES / "D_4A_bulnes.json").read_text(encoding="utf-8"))

#: Categorías de la distribución en el orden en que las imprime el DIA.
COLUMNAS_DIST = ("A", "B", "C", "D", "RC", "RPC", "RI", "N")


def aciertos_por_eje(alumno: dict) -> list[float]:
    """Reconstruye los aciertos crudos de cada eje desde su % redondeado.

    El informe publica porcentajes enteros; los aciertos son múltiplos de 0,5
    (medio punto por respuesta parcialmente correcta en ítems de desarrollo).
    """
    salida = []
    for llave, total in zip(EJE_CLAVES, D["ejeQC"], strict=True):
        salida.append(round(alumno[llave] / 100 * total * 2) / 2)
    return salida


# --- Informe oficial DIA (PDF) -------------------------------------------


def escribir_dia_pdf(destino: pathlib.Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    estilos = getSampleStyleSheet()
    normal, celda = estilos["Normal"], estilos["BodyText"]
    celda.fontSize = 6
    celda.leading = 7

    meta, niveles = D["meta"], D["niveles"]
    flujo = [
        Paragraph("Agencia de la Calidad de la Educación", normal),
        Paragraph("Diagnóstico Integral de Aprendizajes · Monitoreo Intermedio", normal),
        Paragraph(f"ESTABLECIMIENTO: {meta['colegio']}", normal),
        Paragraph(f"RBD: {meta['rbd']}", normal),
        Paragraph(f"CURSO: {meta['curso'].replace(chr(176), chr(176) + ' básico ')}", normal),
        Paragraph(f"DOCENTE: {meta['docente']}", normal),
        Paragraph(f"DIRECTOR: {meta['director']}", normal),
        Paragraph(f"Fecha de aplicación: {meta['fecha']}", normal),
        Spacer(1, 10),
        Paragraph("Distribución por Niveles de Aprendizaje", normal),
    ]
    total = sum(niveles.values())
    nombres = (("I", "Insatisfactorio"), ("II", "Intermedio"), ("III", "Satisfactorio"))
    for romano, nombre in nombres:
        n = niveles[romano]
        flujo.append(
            Paragraph(f"Nivel {romano} · {nombre}: {round(100 * n / total)} % ({n})", normal)
        )

    flujo += [Spacer(1, 10), Paragraph("Resultados por eje temático", normal)]
    for eje, prom in zip(EJES, D["ejeProm"], strict=True):
        flujo.append(Paragraph(f"{eje}: {prom:.1f} %", normal))

    flujo += [Spacer(1, 10), Paragraph("Detalle por pregunta", normal)]
    encabezado = [
        "N° Pregunta", "OA", "Eje", "Habilidad", "Indicador", "% Logro", "Tipo", *COLUMNAS_DIST,
    ]
    filas = [[Paragraph(f"<b>{h}</b>", celda) for h in encabezado]]
    for q in D["questions"]:
        filas.append(
            [
                Paragraph(str(q["q"]), celda),
                Paragraph(str(q["oa"]), celda),
                Paragraph(q["eje"], celda),
                Paragraph(q["hab"], celda),
                Paragraph(q["ind"], celda),
                Paragraph(f"{q['pct']}", celda),
                Paragraph(q["tipo"], celda),
                *[
                    Paragraph("" if k not in q["dist"] else f"{q['dist'][k]:g}", celda)
                    for k in COLUMNAS_DIST
                ],
            ]
        )

    tabla = Table(
        filas,
        colWidths=[30, 18, 60, 50, 196, 26, 40, *([27] * len(COLUMNAS_DIST))],
        repeatRows=1,
    )
    tabla.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    flujo.append(tabla)

    SimpleDocTemplate(
        str(destino), pagesize=landscape(A4), topMargin=18, bottomMargin=18,
        leftMargin=16, rightMargin=16,
    ).build(flujo)


# --- Planillas ------------------------------------------------------------


def _libro(hoja: str, filas: list[list], destino: pathlib.Path, preambulo: int = 2) -> None:
    """Escribe un .xlsx con `preambulo` filas de título antes de la tabla."""
    from openpyxl import Workbook

    libro = Workbook()
    ws = libro.active
    ws.title = hoja
    for _ in range(preambulo):
        ws.append(["Colegio Manuel Bulnes Prieto"])
    for fila in filas:
        ws.append(fila)
    libro.save(destino)


def escribir_estudiantes(destino: pathlib.Path) -> None:
    filas = [["Estudiante", *EJES, "Puntaje obtenido", "Nivel de aprendizaje"]]
    for alumno in D["students"]:
        aciertos = aciertos_por_eje(alumno)
        filas.append(
            [
                alumno["n"],
                *[alumno[k] for k in EJE_CLAVES],
                sum(aciertos),
                {1: "Nivel I", 2: "Nivel II", 3: "Nivel III"}[alumno["lv"]],
            ]
        )
    _libro("Resultados", filas, destino)


def escribir_recomendaciones(destino: pathlib.Path) -> None:
    filas = [
        ["Indicador", "OA", "Unidad JUMP", "Recomendación didáctica", "Análisis adicional"]
    ]
    for rec in D["recs"]:
        unidades = " · ".join(
            f"Tomo {p.split(' · ')[0].strip()} {p.split(' · ')[1].split(' ')[0]}"
            for p in _partes_unidades(rec["units"])
        )
        filas.append([rec["ind"], rec["oa"], unidades, rec["base"], rec["plus"]])
    _libro("Recomendaciones", filas, destino)


def _partes_unidades(units: str) -> list[str]:
    """Parte `"4.1 · U2 Nombre ✓ 85% · 4.2 · U3 Otro ✗"` en unidades sueltas."""
    tokens, actual = [], []
    for token in units.split(" · "):
        actual.append(token)
        if len(actual) == 2:
            tokens.append(" · ".join(actual))
            actual = []
    return tokens


def escribir_seguimiento(destino: pathlib.Path) -> None:
    filas = [["Unidad JUMP", "Evaluación", "Promedio de logro", "Estado"]]
    for cobertura in D["coverage"]:
        registrada = cobertura["status"] == "res"
        filas.append(
            [
                f"Tomo {cobertura['tomo']} · {cobertura['u']} {cobertura['label']}",
                "Control de unidad",
                cobertura["pct"] if registrada else "",
                "Aplicado" if registrada else "Pendiente",
            ]
        )
    _libro("Seguimiento", filas, destino)


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    escribir_dia_pdf(FIXTURES / "dia_oficial_4A.pdf")
    escribir_estudiantes(FIXTURES / "estudiantes_4A.xlsx")
    escribir_recomendaciones(FIXTURES / "recomendaciones_4B.xlsx")
    escribir_seguimiento(FIXTURES / "seguimiento_jump_4A.xlsx")
    for archivo in sorted(FIXTURES.iterdir()):
        print(f"  {archivo.name:32s} {archivo.stat().st_size:>8,} bytes")


if __name__ == "__main__":
    main()
