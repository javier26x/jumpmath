"""Parser del informe oficial DIA (PDF de la Agencia de la Calidad).

Alimenta `meta` y el detalle por pregunta (`questions[]`), que es el corazón
del informe.

Sobre el formato real, que condiciona todo lo de abajo:

- La «Tabla 1. Resultados del curso en cada pregunta» **no tiene rejilla**: es
  texto en columnas, con celdas que envuelven en varias líneas. Por eso no se
  extrae con `extract_tables` sino por coordenadas de palabra.
- Los Gráficos 1 y 2 —niveles de logro y promedio por eje— son **imágenes sin
  capa de texto**. De ahí no se puede leer nada; `ensamblaje` deriva los
  niveles de la nómina oficial y los promedios por eje de las preguntas.
- La alternativa correcta viene «destacada con negrita», pero el PDF no usa una
  fuente bold: simula la negrita rellenando y además trazando el glifo. El
  único rastro es que esos caracteres fijan un color de trazo RGB donde el
  resto deja el gris por defecto. Sin ese detalle habría que adivinar la clave
  por la alternativa más marcada, que es exactamente lo que falla en un ítem
  descendido: en 4° A de Santa Rosa la P7 tiene la clave en B (9,68 %) y dos
  distractores empatados en 38,71 %.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..catalogo import EJES, TIPOS_ITEM, indice_eje
from ..errores import ErrorParseo
from ..normalizacion import a_pct, limpiar, redondear_pct
from ..reglas import logro_mostrado, logro_puntaje, semaforo

FUENTE = "informe oficial DIA"

#: Etiquetas de la columna «% respuestas».
_ALTERNATIVAS = ("A", "B", "C", "D", "E")
_CATEGORIAS = ("RC", "RPC", "RI", "N")

_RE_DIST = re.compile(
    rf"^({'|'.join((*_CATEGORIAS, *_ALTERNATIVAS))})\s*:\s*(\d{{1,3}}(?:[.,]\d+)?)\s*%$"
)
#: Rótulos que sólo coinciden en la fila de encabezado de la tabla. Buscar uno
#: solo no basta: el párrafo que presenta la Tabla 1 dice «habilidad e indicador
#: de evaluación asociado» y se haría pasar por encabezado.
_TOKENS_ENCABEZADO = (
    re.compile(r"eje\s+tem[aá]tico", re.I),
    re.compile(r"habilidad", re.I),
    re.compile(r"indicador\s+de\s+evaluaci[oó]n", re.I),
)
#: Lo primero que aparece bajo la tabla y la da por terminada. «Preguntas guía»
#: importa especialmente: es prosa a todo el ancho de la página y, si entra en
#: la región, fusiona las columnas y la detección de bordes se va al suelo.
_RE_FIN_TABLA = re.compile(
    r"preguntas\s+gu[ií]a|informe\s+de\s+resultados|contin[uú]a\]|continuaci[oó]n\]", re.I
)

#: Tolerancia vertical al agrupar palabras en una misma fila o línea (pt).
_TOL_FILA = 3.0
_TOL_LINEA = 2.0

#: Columnas lógicas de la tabla, en orden de izquierda a derecha.
_COLUMNAS = ("q", "oa", "eje", "hab", "ind", "dist")


@dataclass(slots=True)
class ResultadoDia:
    """Lo que aporta el informe oficial al objeto `D`."""

    meta: dict[str, Any] = field(default_factory=dict)
    niveles: dict[str, int] = field(default_factory=dict)
    ejes: list[str] = field(default_factory=lambda: list(EJES))
    eje_prom: list[float | None] = field(default_factory=lambda: [None] * len(EJES))
    questions: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


# --- Metadatos ------------------------------------------------------------


def _campo(texto: str, etiqueta: str) -> str:
    """Valor de una línea ``Etiqueta: valor`` del encabezado del informe.

    El separador puede venir sin espacio (`Establecimiento:ESCUELA SANTA ROSA`).
    """
    m = re.search(rf"{etiqueta}\s*:\s*(.+)", texto, re.I)
    return limpiar(m.group(1)) if m else ""


def _extraer_meta(texto: str) -> dict[str, Any]:
    """Establecimiento, RBD, curso, docente, director, fecha, N y prueba."""
    meta: dict[str, Any] = {}

    if colegio := _campo(texto, "establecimiento"):
        meta["colegio"] = colegio
    if rbd := _campo(texto, "RBD"):
        meta["rbd"] = re.sub(r"\D", "", rbd)
    if docente := _campo(texto, r"nombre\s+docente(?:\s+de\s+la\s+asignatura)?"):
        meta["docente"] = docente
    if director := _campo(texto, r"nombre\s+director(?:\s+o\s+directora)?"):
        meta["director"] = director

    curso = _campo(texto, "curso")
    if m := re.match(r"(\d)\s*[°ºo]?\s*(?:b[aá]sico\s*)?([A-H])\b", curso, re.I):
        meta["curso"] = f"{m.group(1)}° {m.group(2).upper()}"

    # «Cantidad de estudiantes … : 3 1»: el extractor separa los dígitos, así
    # que se quita todo lo que no sea cifra antes de convertir.
    if digitos := re.sub(r"\D", "", _campo(texto, r"cantidad\s+de\s+estudiantes[^:]*")):
        meta["n"] = int(digitos)

    fecha = _campo(texto, r"fecha\s+y\s+hora\s+de\s+generaci[oó]n[^:]*")
    if m := re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", fecha):
        d, mes, anio = m.groups()
        meta["fecha"] = f"{int(d):02d}/{int(mes):02d}/{anio if len(anio) == 4 else '20' + anio}"

    # Todo informe se titula «Diagnóstico Integral de Aprendizajes», así que ese
    # término aparece antes que el período real: se buscan primero los períodos.
    for patron in (r"monitoreo\s+\w+", r"cierre(?:\s+de\s+a[nñ]o)?", r"diagn[oó]stico"):
        if m := re.search(patron, texto, re.I):
            anio = meta.get("fecha", "")[-4:]
            meta["prueba"] = limpiar(f"DIA · {limpiar(m.group(0)).title()} {anio} · Matemática")
            break

    return meta


# --- Geometría de la tabla ------------------------------------------------


def _bordes_de_columna(palabras: list[dict], columnas: int) -> list[float]:
    """Bordes izquierdos de las columnas de la tabla, deducidos del texto.

    Se proyectan todas las palabras sobre el eje horizontal, se fusiona lo que
    se toca y se corta por los `columnas - 1` huecos más anchos. Los espacios
    entre columnas (17 pt el más estrecho) son muy superiores a los que quedan
    entre palabras de una misma celda, así que el corte cae siempre donde debe
    y no hay márgenes que calibrar a mano.

    Deducirlo del encabezado no serviría: va centrado sobre su columna
    mientras el contenido se alinea a la izquierda, y en la columna del OA el
    desfase (13 pt) es mayor que la separación con la columna vecina.
    """
    if not palabras:
        return []

    union: list[list[float]] = []
    for x0, x1 in sorted((p["x0"], p["x1"]) for p in palabras):
        if union and x0 <= union[-1][1] + 0.5:
            union[-1][1] = max(union[-1][1], x1)
        else:
            union.append([x0, x1])

    if len(union) < columnas:
        return []

    huecos = sorted(
        ((union[i + 1][0] - union[i][1], i) for i in range(len(union) - 1)),
        reverse=True,
    )
    cortes = sorted(i for _, i in huecos[: columnas - 1])
    return [union[0][0]] + [union[i + 1][0] for i in cortes]


def _asignar_columna(x0: float, bordes: list[float]) -> int:
    """Índice de la columna a la que pertenece una palabra, por su borde izquierdo."""
    indice = 0
    for i, borde in enumerate(bordes):
        if x0 >= borde - 1.0:
            indice = i
    return indice


def _region_tabla(palabras: list[dict], alto: float) -> list[dict]:
    """Palabras del cuerpo de la Tabla 1 en esta página.

    Devuelve una lista vacía si la página no contiene la tabla, para no
    interpretar como preguntas los números de otras secciones (el número de
    página del pie, sin ir más lejos).
    """
    lineas = defaultdict(list)
    for p in palabras:
        lineas[round(p["top"] / _TOL_LINEA)].append(p)

    inicio: float | None = None
    fin = alto
    for clave in sorted(lineas):
        texto = " ".join(w["text"] for w in sorted(lineas[clave], key=lambda w: w["x0"]))
        arriba = lineas[clave][0]["top"]
        if inicio is None:
            if all(token.search(texto) for token in _TOKENS_ENCABEZADO):
                inicio = arriba + 10  # el encabezado ocupa dos líneas
        elif arriba > inicio and _RE_FIN_TABLA.search(texto):
            fin = arriba
            break

    if inicio is None:
        return []
    return [p for p in palabras if inicio < p["top"] < fin]


# --- Distribución de respuestas ------------------------------------------


def _es_negrita(palabra: dict) -> bool:
    """`True` si la palabra está destacada, por fuente bold o negrita simulada."""
    fuente = (palabra.get("fontname") or "").lower()
    if any(marca in fuente for marca in ("bold", "black", "heavy", "semibold")):
        return True
    trazo = palabra.get("stroking_color")
    return isinstance(trazo, (list, tuple)) and len(trazo) >= 3


def _distribucion(palabras: list[dict], numero: int, avisos: list[str]) -> tuple[dict, str | None]:
    """Distribución de respuestas y etiqueta de la alternativa correcta.

    Devuelve `(dist, clave)`. `clave` es `None` cuando el destacado no permite
    decidir —ninguna alternativa marcada, o más de una—, y entonces `reglas`
    cae a la más elegida dejando constancia en los avisos.
    """
    lineas: dict[int, list[dict]] = defaultdict(list)
    for p in palabras:
        lineas[round(p["top"] / _TOL_LINEA)].append(p)

    dist: dict[str, float] = {}
    destacadas: list[str] = []
    for clave_linea in sorted(lineas):
        partes = sorted(lineas[clave_linea], key=lambda w: w["x0"])
        texto = "".join(w["text"] for w in partes)
        m = _RE_DIST.match(texto.replace(" ", ""))
        if not m:
            continue
        etiqueta, valor = m.group(1), a_pct(m.group(2))
        if valor is None:
            continue
        dist[etiqueta] = round(valor, 2)
        if etiqueta in _ALTERNATIVAS and all(_es_negrita(w) for w in partes):
            destacadas.append(etiqueta)

    if not dist:
        return {}, None

    hay_alternativas = any(e in dist for e in _ALTERNATIVAS)
    if not hay_alternativas:
        return dist, None  # ítem de RC/RPC: la correcta es RC por definición

    if len(destacadas) == 1:
        return dist, destacadas[0]

    avisos.append(
        f"P{numero}: no se pudo identificar la alternativa correcta por el destacado "
        f"({len(destacadas)} marcadas). Se usa la alternativa más elegida, que puede "
        "no ser la clave."
    )
    return dist, None


def _tipo_item(dist: dict[str, float]) -> str:
    """Clasifica el ítem por las categorías presentes en su distribución."""
    if "RPC" in dist:
        return TIPOS_ITEM[2]  # desarrollo
    if "RC" in dist:
        return TIPOS_ITEM[1]  # completación
    return TIPOS_ITEM[0]  # alternativas


# --- Tabla de preguntas ---------------------------------------------------


def _preguntas_de_pagina(pagina, avisos: list[str]) -> list[dict[str, Any]]:
    """Extrae las preguntas de una página de la Tabla 1."""
    palabras = pagina.extract_words(extra_attrs=["fontname", "stroking_color"])
    if not palabras:
        return []

    cuerpo = _region_tabla(palabras, pagina.height)
    bordes = _bordes_de_columna(cuerpo, len(_COLUMNAS))
    if len(bordes) < len(_COLUMNAS):
        return []

    porcol = defaultdict(list)
    for p in cuerpo:
        porcol[_asignar_columna(p["x0"], bordes)].append(p)

    # Cada fila arranca donde la primera columna trae el número de pregunta.
    inicios = sorted(
        (p["top"], int(p["text"]))
        for p in porcol[0]
        if re.fullmatch(r"\d{1,2}", p["text"])
    )
    if not inicios:
        return []

    preguntas = []
    for i, (arriba, numero) in enumerate(inicios):
        abajo = inicios[i + 1][0] - _TOL_FILA if i + 1 < len(inicios) else pagina.height
        banda = {
            col: [p for p in porcol[j] if arriba - _TOL_FILA <= p["top"] < abajo]
            for j, col in enumerate(_COLUMNAS)
        }

        def texto(col: str, banda: dict = banda) -> str:
            """Contenido de una celda, uniendo sus líneas envueltas en orden."""
            partes = sorted(banda[col], key=lambda w: (w["top"], w["x0"]))
            return limpiar(" ".join(p["text"] for p in partes))

        dist, clave = _distribucion(banda["dist"], numero, avisos)
        if not dist:
            avisos.append(f"P{numero}: sin distribución de respuestas legible; se omite.")
            continue
        if clave:
            dist["clave"] = clave

        tipo = _tipo_item(dist)
        mostrado = logro_mostrado(tipo, dist)
        try:
            eje = EJES[indice_eje(texto("eje"))]
        except KeyError:
            eje = ""
            avisos.append(f"P{numero}: eje «{texto('eje')}» no reconocido.")

        oa = re.sub(r"\D", "", texto("oa"))
        preguntas.append(
            {
                "q": numero,
                "oa": int(oa) if oa else 0,
                "eje": eje,
                "hab": texto("hab"),
                # Redacción textual del informe oficial (guía §4).
                "ind": texto("ind"),
                "pct": redondear_pct(mostrado),
                "sem": semaforo(mostrado),
                "puntaje_exacto": round(logro_puntaje(tipo, dist), 2),
                "tipo": tipo,
                "dist": dist,
            }
        )
    return preguntas


def parsear_dia_oficial(datos: bytes, nombre_archivo: str = "dia.pdf") -> ResultadoDia:
    """Lee el PDF oficial del DIA y devuelve su aporte al objeto `D`."""
    origen = f"{FUENTE} · {nombre_archivo}"
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependencia de despliegue
        raise ErrorParseo(origen, f"falta pdfplumber para leer el PDF: {exc}") from exc

    resultado = ResultadoDia()
    vistas: dict[int, dict[str, Any]] = {}

    try:
        with pdfplumber.open(io.BytesIO(datos)) as pdf:
            textos = []
            for pagina in pdf.pages:
                textos.append(pagina.extract_text() or "")
                for pregunta in _preguntas_de_pagina(pagina, resultado.avisos):
                    vistas.setdefault(pregunta["q"], pregunta)
    except ErrorParseo:
        raise
    except Exception as exc:
        raise ErrorParseo(origen, f"no se pudo leer el PDF: {exc}") from exc

    texto = "\n".join(textos)
    if not texto.strip():
        raise ErrorParseo(
            origen,
            "el PDF no contiene texto extraíble (¿escaneado?). "
            "Active el OCR de Document AI con JUMPDIA_DOCAI_PROCESSOR.",
        )

    resultado.meta = _extraer_meta(texto)
    resultado.questions = [vistas[n] for n in sorted(vistas)]

    if not resultado.questions:
        raise ErrorParseo(
            origen,
            "no se encontró la «Tabla 1. Resultados del curso en cada pregunta». "
            "Se esperan las columnas N° pregunta, N° OA, Eje temático, Habilidad, "
            "Indicador de evaluación y % respuestas.",
        )

    # Los Gráficos 1 y 2 son imágenes: sus datos no están en el PDF. `ensamblaje`
    # los reconstruye desde la nómina oficial y desde las preguntas.
    resultado.avisos.append(
        "los niveles de logro y el promedio por eje están en gráficos sin capa de "
        "texto: se toman de la nómina oficial y del detalle por pregunta."
    )
    return resultado
