"""Parsers de los archivos de origen del informe DIA."""

from .dia_oficial import parsear_dia_oficial
from .estudiantes import parsear_estudiantes
from .plan_anual import parsear_plan_anual
from .recomendaciones import parsear_recomendaciones
from .seguimiento import parsear_seguimiento

__all__ = [
    "parsear_dia_oficial",
    "parsear_estudiantes",
    "parsear_plan_anual",
    "parsear_recomendaciones",
    "parsear_seguimiento",
]
