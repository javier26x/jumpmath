"""Backend de ingesta del Informe DIA · 4° Básico · JUMP Math.

Convierte los archivos que sube el docente (informe oficial DIA, resultados
por estudiante, recomendaciones por indicador y seguimiento de evaluaciones
JUMP) en el objeto `D` que consume el HTML del informe.

Uso mínimo::

    from jumpdia import Archivo, Entrada, ensamblar

    salida = ensamblar(Entrada(
        dia_oficial=Archivo("dia.pdf", datos_pdf),
        estudiantes=Archivo("estudiantes.xlsx", datos_xlsx),
        recomendaciones=Archivo("recomendaciones.xlsx", datos_rec),
        seguimiento=Archivo("seguimiento.xlsx", datos_seg),
    ))
    salida.D        # objeto D validado
    salida.avisos   # qué hubo que asumir por el camino
"""

from __future__ import annotations

from .catalogo import EJES, TIPOS_ITEM, UNIDADES_JUMP
from .ensamblaje import Archivo, Entrada, Salida, ensamblar
from .errores import ErrorIngesta, ErrorParseo, ErrorValidacion
from .render import inyectar_D, preparar_informe
from .validacion import validar

__version__ = "1.0.0"

__all__ = [
    "Archivo",
    "EJES",
    "Entrada",
    "ErrorIngesta",
    "ErrorParseo",
    "ErrorValidacion",
    "Salida",
    "TIPOS_ITEM",
    "UNIDADES_JUMP",
    "ensamblar",
    "inyectar_D",
    "preparar_informe",
    "validar",
]
