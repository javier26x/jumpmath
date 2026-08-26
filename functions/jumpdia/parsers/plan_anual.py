"""Parser del Plan Anual del curso (.xlsx o PDF) — archivo **opcional**.

No alimenta ningún campo obligatorio de `D`: aporta la secuencia esperada por
fecha, que el informe usa como nota de contexto en la sección de cobertura
(«a la fecha de aplicación, el curso debería ir en…»).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..normalizacion import limpiar
from .planilla import Columna, localizar_tabla
from .recomendaciones import extraer_unidades

FUENTE = "plan anual"

_COLUMNAS = (
    Columna("unidad", ("unidad", "unidad jump", "tomo y unidad", "contenido", "tomo")),
    Columna("periodo", ("mes", "fecha", "periodo", "semana", "inicio"), requerida=False),
)


@dataclass(slots=True)
class ResultadoPlanAnual:
    #: clave de unidad JUMP → período en que se planificó
    secuencia: dict[str, str] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def parsear_plan_anual(datos: bytes, nombre_archivo: str) -> ResultadoPlanAnual:
    """Lee la secuencia planificada; devuelve un resultado vacío si no calza."""
    resultado = ResultadoPlanAnual()
    try:
        tabla = localizar_tabla(datos, nombre_archivo, _COLUMNAS)
    except Exception as exc:  # el plan anual es opcional: nunca aborta la ingesta
        resultado.avisos.append(f"plan anual ignorado: {exc}")
        return resultado

    for registro in tabla.registros():
        for unidad in extraer_unidades(registro.get("unidad")):
            resultado.secuencia.setdefault(unidad.clave, limpiar(registro.get("periodo")))
    return resultado


def nota_cobertura(secuencia: dict[str, Any], coverage: list[dict[str, Any]]) -> str:
    """Texto de contexto que compara lo planificado con lo efectivamente registrado."""
    if not secuencia:
        return ""
    planificadas = {c for c in secuencia}
    registradas = {f"{c['tomo']}/{c['u']}" for c in coverage if c["status"] == "res"}
    pendientes = [c for c in planificadas if c not in registradas]
    if not pendientes:
        return "Todas las unidades planificadas a la fecha tienen control o prueba registrada."
    return (
        f"{len(pendientes)} de {len(planificadas)} unidades planificadas no tienen "
        "control o prueba registrada a la fecha: "
        + ", ".join(sorted(pendientes))
        + ". Puede tratarse de unidades trabajadas sin registrar o con evaluación pendiente."
    )
