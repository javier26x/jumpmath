"""Inyección del objeto `D` en la plantilla HTML del informe.

El prototipo es un único archivo autocontenido con `const D={…}` al inicio de
su `<script>`. Servir el informe de otro curso es reemplazar ese literal: no
hay build ni framework de por medio (guía §2 y §3).
"""

from __future__ import annotations

import json
import re
from typing import Any

_MARCA = "const D="
#: Cierra `</script>` dentro de un literal JSON incrustado en HTML.
_ESCAPES = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", " ": "\\u2028", " ": "\\u2029"}


def serializar_D(D: dict[str, Any]) -> str:
    """`D` como literal JS seguro para incrustar dentro de `<script>`.

    Los campos `base`/`plus` de las recomendaciones admiten HTML (`<b>`), así
    que un `</script>` en el texto cerraría el bloque antes de tiempo. Se
    escapan los caracteres que pueden romper el parseo del documento; el JSON
    resultante sigue siendo equivalente.
    """
    crudo = json.dumps(D, ensure_ascii=False, separators=(", ", ": "))
    return re.sub(r"[<>&  ]", lambda m: _ESCAPES[m.group()], crudo)


def inyectar_D(plantilla: str, D: dict[str, Any]) -> str:
    """Devuelve el HTML del informe con `D` reemplazado por el del curso."""
    inicio = plantilla.find(_MARCA)
    if inicio == -1:
        raise ValueError(f"la plantilla no contiene «{_MARCA}»")
    cuerpo = inicio + len(_MARCA)
    _, fin = json.JSONDecoder().raw_decode(plantilla, cuerpo)
    return plantilla[:cuerpo] + serializar_D(D) + plantilla[fin:]
