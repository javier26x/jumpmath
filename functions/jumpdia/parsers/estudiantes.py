"""Parser de «Resultados por estudiante» (.xlsx o PDF).

Alimenta `D.students[]` y `D.meta.n`. El nivel de aprendizaje (`lv`) es el
oficial del DIA y se copia tal cual: **no** se deriva del porcentaje global
(guía §4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..catalogo import EJE_CLAVES, EJES
from ..errores import ErrorParseo
from ..normalizacion import a_float, a_pct, clave, es_vacio, limpiar
from .planilla import Columna, localizar_tabla

FUENTE = "resultados por estudiante"

_ROMANOS = {"I": 1, "II": 2, "III": 3}

_COLUMNAS = (
    Columna("nombre", ("estudiante", "nombre", "alumno", "apellidos y nombres", "nombre completo")),
    Columna("nyo", ("numeros y operaciones", "numeros", "n y o", "nyo")),
    Columna("pa", ("patrones y algebra", "patrones", "algebra", "pa")),
    Columna("geo", ("geometria", "geo")),
    Columna("med", ("medicion", "med")),
    Columna("dyp", ("datos y probabilidades", "datos y azar", "datos", "dyp")),
    Columna("nivel", ("nivel", "nivel de aprendizaje", "nivel dia", "categoria de desempeno")),
    Columna(
        "global",
        ("global", "total", "porcentaje de logro", "logro global", "% logro"),
        requerida=False,
    ),
    Columna("puntaje", ("puntaje", "puntaje obtenido", "aciertos", "correctas"), requerida=False),
)


@dataclass(slots=True)
class ResultadoEstudiantes:
    students: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _nivel(valor: object) -> int | None:
    """Nivel oficial como 1/2/3, aceptando romanos, dígitos o el nombre."""
    texto = limpiar(valor)
    if es_vacio(texto):
        return None
    plano = clave(texto)
    if m := re.search(r"\bnivel\s+(i{1,3})\b", plano):
        return _ROMANOS[m.group(1).upper()]
    if plano.upper() in _ROMANOS:
        return _ROMANOS[plano.upper()]
    for nombre, nivel in (("insatisfactorio", 1), ("intermedio", 2), ("satisfactorio", 3)):
        if nombre in plano:
            return nivel
    n = a_float(texto)
    return int(n) if n is not None and 1 <= n <= 3 else None


def parsear_estudiantes(datos: bytes, nombre_archivo: str) -> ResultadoEstudiantes:
    """Lee la nómina con % por eje y nivel oficial de cada estudiante."""
    if nombre_archivo.lower().endswith(".pdf"):
        datos, nombre_archivo = _pdf_a_filas(datos, nombre_archivo)

    tabla = localizar_tabla(datos, nombre_archivo, _COLUMNAS)
    resultado = ResultadoEstudiantes()

    for registro in tabla.registros():
        nombre = limpiar(registro.get("nombre"))
        if not nombre or clave(nombre) in ("total", "promedio", "promedio curso", "curso"):
            continue

        alumno: dict[str, Any] = {"n": nombre}
        for llave in EJE_CLAVES:
            pct = a_pct(registro.get(llave))
            if pct is None:
                resultado.avisos.append(
                    f"{nombre}: sin % en «{EJES[EJE_CLAVES.index(llave)]}», se asume 0"
                )
            alumno[llave] = round(pct or 0.0, 2)

        nivel = _nivel(registro.get("nivel"))
        if nivel is None:
            raise ErrorParseo(
                FUENTE,
                f"«{nombre}» no trae nivel de aprendizaje. El nivel es oficial del DIA "
                "y no puede calcularse desde el % de logro.",
            )
        alumno["lv"] = nivel

        # Opcionales: permiten calcular el global exacto en vez de aproximarlo.
        if (puntaje := a_float(registro.get("puntaje"))) is not None:
            alumno["puntaje_crudo"] = puntaje
        if (g := a_pct(registro.get("global"))) is not None:
            alumno["g_informado"] = round(g, 2)

        resultado.students.append(alumno)

    if not resultado.students:
        raise ErrorParseo(FUENTE, "la tabla no contiene estudiantes")
    return resultado


def _pdf_a_filas(datos: bytes, nombre_archivo: str) -> tuple[bytes, str]:
    """Convierte la tabla del PDF a un CSV en memoria y lo reencamina.

    Reutiliza `localizar_tabla` en vez de duplicar la búsqueda de encabezados:
    lo único distinto entre el PDF y el .xlsx es cómo se llega a las celdas.
    """
    try:
        import io

        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependencia de despliegue
        raise ErrorParseo(FUENTE, f"falta pdfplumber para leer el PDF: {exc}") from exc

    filas: list[list[str]] = []
    with pdfplumber.open(io.BytesIO(datos)) as pdf:
        for pagina in pdf.pages:
            for tabla in pagina.extract_tables() or []:
                filas.extend([limpiar(c) for c in fila] for fila in tabla)

    if not filas:
        raise ErrorParseo(FUENTE, "el PDF no contiene tablas extraíbles")

    import csv
    import io as _io

    buffer = _io.StringIO()
    csv.writer(buffer).writerows(filas)
    return buffer.getvalue().encode("utf-8"), nombre_archivo.rsplit(".", 1)[0] + ".csv"
