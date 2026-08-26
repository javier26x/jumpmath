"""Parser de «Recomendaciones por indicador 4° BP» (.xlsx).

Alimenta `recs[].{base, plus}` y —lo más importante— el mapeo
**indicador → unidad JUMP** (Tomo 4.1 / 4.2) del que dependen `recs[].units`
y `recs[].estado`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..catalogo import POR_CLAVE, UnidadJump
from ..errores import ErrorParseo
from ..normalizacion import clave, es_vacio, limpiar, texto_largo
from .planilla import Columna, localizar_tabla

FUENTE = "recomendaciones por indicador"

#: "Tomo 4.1 U2", "4.1·U2", "4.1 - Unidad 2" … → ("4.1", "U2")
_RE_UNIDAD = re.compile(
    r"(?:tomo\s*)?(4\s*[.,]\s*[12])\s*[·\-–—/ ]*\s*(?:u(?:nidad)?\s*)?([1-8])\b", re.I
)

_COLUMNAS = (
    Columna("ind", ("indicador", "indicador de evaluacion", "descripcion del indicador")),
    Columna("unidades", ("unidad", "unidad jump", "unidades jump", "tomo y unidad", "tomo")),
    Columna(
        "base", ("recomendacion", "recomendacion didactica", "sugerencia", "orientaciones")
    ),
    Columna(
        "plus",
        ("analisis", "analisis adicional", "comentario", "nota jump", "plus"),
        requerida=False,
    ),
    Columna("oa", ("oa", "objetivo de aprendizaje"), requerida=False),
)


@dataclass(slots=True)
class ResultadoRecomendaciones:
    #: clave normalizada del indicador → texto base de la recomendación
    base: dict[str, str] = field(default_factory=dict)
    #: clave normalizada del indicador → análisis complementario (puede ir vacío)
    plus: dict[str, str] = field(default_factory=dict)
    #: clave normalizada del indicador → unidades JUMP que lo cubren
    unidades: dict[str, list[UnidadJump]] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def extraer_unidades(texto: object) -> list[UnidadJump]:
    """Extrae las unidades JUMP citadas en una celda, sin repetir y en orden."""
    encontradas: list[UnidadJump] = []
    for tomo, numero in _RE_UNIDAD.findall(limpiar(texto)):
        unidad = POR_CLAVE.get(f"{tomo.replace(' ', '').replace(',', '.')}/U{numero}")
        if unidad is not None and unidad not in encontradas:
            encontradas.append(unidad)
    return encontradas


def parsear_recomendaciones(datos: bytes, nombre_archivo: str) -> ResultadoRecomendaciones:
    """Lee la planilla de recomendaciones y su mapeo a unidades JUMP."""
    tabla = localizar_tabla(datos, nombre_archivo, _COLUMNAS)
    resultado = ResultadoRecomendaciones()

    for registro in tabla.registros():
        indicador = limpiar(registro.get("ind"))
        if not indicador or es_vacio(indicador):
            continue
        llave = clave(indicador)

        unidades = extraer_unidades(registro.get("unidades"))
        if not unidades:
            resultado.avisos.append(
                f"«{indicador[:60]}…»: no se reconoció ninguna unidad JUMP en "
                f"«{limpiar(registro.get('unidades'))[:40]}»"
            )
        resultado.unidades[llave] = unidades
        resultado.base[llave] = texto_largo(registro.get("base"))
        resultado.plus[llave] = texto_largo(registro.get("plus"))

    if not resultado.base:
        raise ErrorParseo(FUENTE, "la planilla no contiene indicadores")
    return resultado
