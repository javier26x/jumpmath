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


#: Etiqueta que engancha la aplicación con la plantilla. En un informe ya
#: generado no pinta nada: el Paso 1 se cumplió y no hay nada que subir.
_MARCA_APP = '<script type="module" src="/app.js"></script>'

_ESTILO_INFORME = (
    "<style>/* Informe generado: el Paso 1 ya se cumplió. */\n"
    "#uploadPanel{display:none!important}</style>\n"
)


def preparar_informe(plantilla: str, D: dict[str, Any]) -> str:
    """HTML del informe de un curso, listo para servir por sí solo.

    Es el mismo archivo que la aplicación, con el `D` del curso y sin la
    cáscara: se quita el script que conecta el Paso 1 y se oculta el panel de
    carga, que en un informe ya generado sólo invita a subir los archivos otra
    vez. Lo que queda es lo que describe la guía §3: un HTML autocontenido.
    """
    html = inyectar_D(plantilla, D)
    html = html.replace(_MARCA_APP, "")
    if "</head>" in html:
        return html.replace("</head>", _ESTILO_INFORME + "</head>", 1)
    return _ESTILO_INFORME + html


def inyectar_D(plantilla: str, D: dict[str, Any]) -> str:
    """Devuelve el HTML del informe con `D` reemplazado por el del curso."""
    inicio = plantilla.find(_MARCA)
    if inicio == -1:
        raise ValueError(f"la plantilla no contiene «{_MARCA}»")
    cuerpo = inicio + len(_MARCA)
    _, fin = json.JSONDecoder().raw_decode(plantilla, cuerpo)
    return plantilla[:cuerpo] + serializar_D(D) + plantilla[fin:]
