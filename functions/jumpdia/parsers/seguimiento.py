"""Parser del «Seguimiento de evaluaciones JUMP» (controles y pruebas, .xlsx).

Alimenta `D.coverage[]`. Regla central de la guía (§4): sólo se marca
`status:'res'` una unidad con control o prueba **registrada**. La ausencia de
registro es `status:'none'` y **no** significa "no trabajada" — puede estar
trabajada sin registrar o con la prueba pendiente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..catalogo import UNIDADES_JUMP
from ..normalizacion import a_pct, clave, es_vacio
from .planilla import Columna, localizar_tabla
from .recomendaciones import extraer_unidades

FUENTE = "seguimiento de evaluaciones JUMP"

_COLUMNAS = (
    Columna("unidad", ("unidad", "unidad jump", "tomo y unidad", "control", "evaluacion", "tomo")),
    Columna("pct", ("promedio", "logro", "porcentaje", "% logro", "resultado", "promedio curso")),
    Columna("estado", ("estado", "aplicado", "rendido", "registrado"), requerida=False),
)


@dataclass(slots=True)
class ResultadoSeguimiento:
    coverage: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def parsear_seguimiento(datos: bytes, nombre_archivo: str) -> ResultadoSeguimiento:
    """Construye la cobertura JUMP en el orden curricular del catálogo."""
    tabla = localizar_tabla(datos, nombre_archivo, _COLUMNAS)
    registrados: dict[str, float] = {}
    resultado = ResultadoSeguimiento()

    for registro in tabla.registros():
        unidades = extraer_unidades(registro.get("unidad"))
        if not unidades:
            continue

        estado = clave(registro.get("estado"))
        if estado in ("pendiente", "no aplicado", "no rendido", "no"):
            continue

        pct = a_pct(registro.get("pct"))
        if pct is None or es_vacio(registro.get("pct")):
            # Sin resultado registrado: queda como 'none', no como 0 %.
            continue

        for unidad in unidades:
            anterior = registrados.get(unidad.clave)
            if anterior is not None:
                resultado.avisos.append(
                    f"{unidad.clave} tiene más de un registro ({anterior:.0f}% y {pct:.0f}%); "
                    "se usa el último"
                )
            registrados[unidad.clave] = pct

    for unidad in UNIDADES_JUMP:
        pct = registrados.get(unidad.clave)
        resultado.coverage.append(
            {
                "tomo": unidad.tomo,
                "u": unidad.u,
                "label": unidad.label,
                "status": "res" if pct is not None else "none",
                "pct": round(pct, 1) if pct is not None else None,
            }
        )

    if not registrados:
        resultado.avisos.append(
            "no se registró ningún control o prueba: toda la cobertura queda "
            "en 'none' (sin registro), que no equivale a 'no trabajada'"
        )
    return resultado
