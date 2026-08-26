"""Utilidades de normalización de texto y de porcentajes.

Los archivos de origen (PDF del DIA, planillas del colegio) traen la misma
información escrita de formas distintas: tildes inconsistentes, espacios
duros, «%» pegado, comas decimales, guiones para «sin dato». Todo eso se
resuelve aquí para que los parsers trabajen sobre valores limpios.
"""

from __future__ import annotations

import re
import unicodedata

_ESPACIOS = re.compile(r"[\s   ]+")
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")

#: Marcadores usados en las planillas para "sin registro".
VACIOS: frozenset[str] = frozenset({"", "-", "--", "—", "–", "s/i", "sin dato", "n/a", "na", "nd"})


def sin_tildes(texto: str) -> str:
    """Quita diacríticos conservando la letra base (``"Medición" -> "Medicion"``)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def limpiar(texto: object) -> str:
    """Colapsa espacios (incluidos los no separables) y recorta los extremos."""
    if texto is None:
        return ""
    return _ESPACIOS.sub(" ", str(texto)).strip()


def texto_largo(valor: object) -> str:
    """Normaliza un texto extenso **sin** colapsar sus espacios internos.

    Para campos de prosa (las recomendaciones didácticas, que el docente copia
    y pega a su planificación) se unifican los saltos de línea y los espacios
    no separables, pero se conserva la separación original entre frases. Usar
    `limpiar` aquí reescribiría el texto de la planilla.
    """
    if valor is None:
        return ""
    texto = str(valor).replace("\r\n", "\n").replace("\r", "\n")
    return texto.replace("\n", " ").replace("\xa0", " ").replace("\u202f", " ").strip()


def clave(texto: object) -> str:
    """Clave de comparación: sin tildes, sin puntuación y en minúsculas.

    Sirve para casar el mismo indicador escrito en el PDF del DIA y en la
    planilla de recomendaciones, donde la puntuación final suele variar.
    """
    plano = sin_tildes(limpiar(texto)).lower()
    return _ESPACIOS.sub(" ", re.sub(r"[^\w\s]", " ", plano)).strip()


def es_vacio(valor: object) -> bool:
    """`True` si la celda representa ausencia de dato."""
    return limpiar(valor).lower() in VACIOS


def a_float(valor: object) -> float | None:
    """Extrae un número de una celda (`"84,6 %"` → ``84.6``); `None` si no hay."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = limpiar(valor)
    if es_vacio(texto):
        return None
    m = _NUM.search(texto.replace(",", "."))
    return float(m.group()) if m else None


def a_pct(valor: object) -> float | None:
    """Normaliza un porcentaje a la escala 0–100.

    Acepta ``84``, ``"84,6%"`` y la fracción ``0.846`` que producen algunas
    planillas de cálculo. La fracción sólo se reescala cuando el valor está en
    ``(0, 1]`` y la celda no traía un signo «%» explícito, para no convertir
    por error un logro real de 1 %.
    """
    n = a_float(valor)
    if n is None:
        return None
    literal_pct = isinstance(valor, str) and "%" in valor
    if 0 < n <= 1 and not literal_pct:
        n *= 100.0
    return max(0.0, min(100.0, n))


def redondear_pct(valor: float) -> int:
    """Redondeo comercial (medio hacia arriba) al entero que muestra el informe.

    `round()` de Python usa redondeo bancario: ``round(69.5) == 70`` pero
    ``round(50.5) == 50``. El informe redondea siempre hacia arriba en el .5.
    """
    from decimal import ROUND_HALF_UP, Decimal

    return int(Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
