"""Parser del informe oficial DIA (PDF de la Agencia de la Calidad).

Alimenta `meta`, `niveles`, `ejes`, `ejeProm` y el detalle por pregunta
(`questions[]`). Es la fuente de verdad para los niveles de aprendizaje: la
guía prohíbe recalcularlos con cortes de porcentaje (§4).

El PDF no tiene un formato tabular estable entre versiones, así que la
extracción está partida en extractores independientes: si uno falla, el
diagnóstico apunta a la sección concreta en vez de invalidar todo el archivo.
Se intenta primero la extracción de tablas (`pdfplumber`) y se cae a un
barrido por texto cuando el PDF no trae rejilla dibujada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..catalogo import EJES, TIPOS_ITEM, indice_eje
from ..errores import ErrorParseo
from ..normalizacion import a_float, a_pct, clave, limpiar, redondear_pct
from ..reglas import logro_mostrado, logro_puntaje, semaforo

FUENTE = "informe oficial DIA"

# Alternativas y categorías de respuesta que usa la Agencia.
_ALTERNATIVAS = ("A", "B", "C", "D", "E")
_CATEGORIAS = ("RC", "RPC", "RI", "N")

_RE_RBD = re.compile(r"RBD\s*[:·º°N#]*\s*(\d{3,7})", re.I)
_RE_CURSO = re.compile(r"\b(\d)\s*[°ºo]?\s*(?:b[aá]sico\s*)?([A-H])\b", re.I)
_RE_FECHA = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
_RE_CONTEO_NIVEL = re.compile(
    r"nivel\s+(I{1,3})\s*(?:·|-|:)?\s*(?:insatisfactorio|intermedio|satisfactorio)?"
    r"[^\d%]{0,40}(\d{1,3})\s*%?[^\d]{0,10}\(?\s*(\d{1,3})\s*\)?",
    re.I,
)
_RE_TIPO = {
    "desarrollo": re.compile(r"desarrollo|respuesta\s+construida|abierta", re.I),
    "completacion": re.compile(r"completaci[oó]n|completar", re.I),
    "alternativas": re.compile(r"alternativas?|selecci[oó]n\s+m[uú]ltiple", re.I),
}


@dataclass(slots=True)
class ResultadoDia:
    """Lo que aporta el informe oficial al objeto `D`."""

    meta: dict[str, Any] = field(default_factory=dict)
    niveles: dict[str, int] = field(default_factory=dict)
    ejes: list[str] = field(default_factory=lambda: list(EJES))
    eje_prom: list[float | None] = field(default_factory=lambda: [None] * len(EJES))
    questions: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


# --- Lectura del PDF ------------------------------------------------------


def _paginas(datos: bytes, archivo: str) -> tuple[list[str], list[list[list[str]]]]:
    """Devuelve `(texto_por_pagina, tablas_por_pagina)`.

    `archivo` sólo se usa en los mensajes de error: quien sube cinco archivos
    necesita saber cuál de ellos falló.
    """
    origen = f"{FUENTE} · {archivo}"
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependencia de despliegue
        raise ErrorParseo(origen, f"falta pdfplumber para leer el PDF: {exc}") from exc

    textos: list[str] = []
    tablas: list[list[list[str]]] = []
    try:
        import io

        with pdfplumber.open(io.BytesIO(datos)) as pdf:
            for pagina in pdf.pages:
                textos.append(pagina.extract_text() or "")
                for tabla in pagina.extract_tables() or []:
                    # Se conserva el texto crudo: los saltos de línea dentro de
                    # una celda son la única pista para recomponer un
                    # encabezado que el PDF partió («N° Preg\nunta»).
                    tablas.append([[c or "" for c in fila] for fila in tabla])
    except Exception as exc:
        raise ErrorParseo(origen, f"no se pudo abrir el PDF: {exc}") from exc

    if not any(t.strip() for t in textos):
        raise ErrorParseo(
            origen,
            "el PDF no contiene texto extraíble (¿escaneado?). "
            "Active el OCR de Document AI con JUMPDIA_DOCAI_PROCESSOR.",
        )
    return textos, tablas


# --- Extractores por sección ---------------------------------------------


def _extraer_meta(texto: str) -> dict[str, Any]:
    """Establecimiento, RBD, curso, docente, director, fecha y prueba."""
    meta: dict[str, Any] = {}

    if m := _RE_RBD.search(texto):
        meta["rbd"] = m.group(1)
    if m := _RE_CURSO.search(texto):
        meta["curso"] = f"{m.group(1)}° {m.group(2).upper()}"
    if m := _RE_FECHA.search(texto):
        d, mth, y = m.groups()
        y = y if len(y) == 4 else f"20{y}"
        meta["fecha"] = f"{int(d):02d}/{int(mth):02d}/{y}"

    for etiqueta, destino in (
        ("establecimiento", "colegio"),
        ("colegio", "colegio"),
        ("docente", "docente"),
        ("profesor", "docente"),
        ("director", "director"),
        ("directora", "director"),
    ):
        if destino in meta:
            continue
        patron = re.compile(rf"{etiqueta}\s*[:·]?\s*\n?\s*([^\n]{{3,90}})", re.I)
        if m := patron.search(texto):
            valor = limpiar(m.group(1)).strip(":·-— ")
            if valor and not valor.lower().startswith(("rbd", "curso")):
                meta[destino] = valor

    # Todo informe DIA se titula «Diagnóstico Integral de Aprendizajes», así que
    # ese término aparece antes en el texto que el período real. Se buscan los
    # períodos concretos primero y sólo se cae a «Diagnóstico» si no hay otro.
    for patron in (r"monitoreo\s+\w+", r"cierre(?:\s+de\s+a[nñ]o)?", r"diagn[oó]stico"):
        if m := re.search(patron, texto, re.I):
            periodo = limpiar(m.group(0)).title()
            anio = meta.get("fecha", "")[-4:] or ""
            meta["prueba"] = limpiar(f"DIA · {periodo} {anio} · Matemática")
            break

    return meta


def _extraer_niveles(texto: str) -> dict[str, int]:
    """Conteo de estudiantes por nivel oficial (I, II, III).

    Nunca se derivan de cortes de porcentaje: son la clasificación de la
    Agencia y un estudiante puede tener <60 % global y estar en Nivel II.
    """
    niveles: dict[str, int] = {}
    for m in _RE_CONTEO_NIVEL.finditer(texto):
        romano, primero, segundo = m.group(1).upper(), m.group(2), m.group(3)
        # El informe imprime "50 % Nivel III · Satisfactorio (13)":
        # el número entre paréntesis es el conteo, el otro el porcentaje.
        conteo = int(segundo) if segundo is not None else int(primero)
        niveles.setdefault(romano, conteo)
    return {r: niveles[r] for r in ("I", "II", "III") if r in niveles}


def _extraer_eje_prom(texto: str) -> list[float | None]:
    """% promedio de logro por eje, en el orden canónico de `EJES`."""
    proms: list[float | None] = [None] * len(EJES)
    for linea in texto.splitlines():
        plano = clave(linea)
        for i, eje in enumerate(EJES):
            if proms[i] is not None or clave(eje) not in plano:
                continue
            if m := re.search(r"(\d{1,3}(?:[.,]\d)?)\s*%", linea):
                proms[i] = a_pct(m.group(1))
    return proms


def _tipo_item(texto: str, dist: dict[str, float]) -> str:
    """Clasifica el ítem por su texto y, si no lo dice, por su distribución."""
    for tipo, patron in _TIPOS_ORDENADOS:
        if patron.search(texto):
            return tipo
    if "RPC" in dist:
        return TIPOS_ITEM[2]
    if "RC" in dist:
        return TIPOS_ITEM[1]
    return TIPOS_ITEM[0]


_TIPOS_ORDENADOS = [
    (TIPOS_ITEM[2], _RE_TIPO["desarrollo"]),
    (TIPOS_ITEM[1], _RE_TIPO["completacion"]),
    (TIPOS_ITEM[0], _RE_TIPO["alternativas"]),
]


def _sin_corte(valor: Any) -> Any:
    """Recompone una cifra que el ajuste de línea partió dentro de una celda.

    Una columna estrecha parte «100» como ``"10\n0"`` y «38,46» como
    ``"38,4\n6"``. Quitar el salto —sin insertar espacio— restituye el número.
    """
    if isinstance(valor, str):
        return valor.replace("\n", "").replace("\r", "")
    return valor


def _entero_celda(valor: Any) -> int | None:
    """Cifra de conteo (N° de pregunta, OA): nunca pasa por la escala de %."""
    n = a_float(_sin_corte(valor))
    return int(n) if n is not None else None


def _pct_celda(valor: Any) -> float | None:
    """Porcentaje de una celda de PDF, recomponiendo cifras partidas en dos líneas.

    Se separa de `_entero_celda` a propósito: `a_pct` reescala el rango (0, 1]
    porque las planillas guardan «84,6 %» como 0.846, y aplicar eso a un número
    de pregunta convertiría la P1 en un 100.
    """
    return a_pct(_sin_corte(valor))


def _distribucion(celdas: dict[str, Any]) -> dict[str, float]:
    """Distribución de respuestas del ítem, filtrando categorías ausentes."""
    dist: dict[str, float] = {}
    for etiqueta in (*_CATEGORIAS, *_ALTERNATIVAS):
        valor = celdas.get(etiqueta)
        if valor is None or isinstance(valor, bool):
            continue
        if (pct := _pct_celda(valor)) is not None:
            dist[etiqueta] = round(pct, 2)
    return dist


def _claves_encabezado(celda: str) -> tuple[str, str]:
    """Dos lecturas de un encabezado que el PDF partió en varias líneas.

    Una tabla de PDF envuelve el texto dentro de la celda, así que «N° Pregunta»
    llega como ``"N° Preg\nunta"`` y «OA» como ``"O\nA"``. Uniendo sin espacio se
    recupera la palabra cortada; uniendo con espacio se conserva un encabezado
    que de verdad tenía dos palabras. Se prueban ambas.
    """
    return clave(celda.replace("\n", "")), clave(celda.replace("\n", " "))


def _clasificar_columna(celda: str) -> str | None:
    """Columna lógica de un encabezado, o `None` si no se reconoce.

    El orden importa: las categorías de respuesta (``A``…``E``, ``RC``, ``N``)
    se evalúan **antes** que cualquier patrón laxo, porque la columna «N» de
    omisión se confundiría con una «N°» de pregunta y arruinaría el número de
    ítem de toda la tabla.
    """
    for h in _claves_encabezado(celda):
        if not h:
            continue
        if h.upper() in (*_CATEGORIAS, *_ALTERNATIVAS):
            return h.upper()
        if "indicador" in h:
            return "ind"
        if "habilidad" in h:
            return "hab"
        if re.fullmatch(r"oa|o a|objetivo(\s+de\s+aprendizaje)?", h):
            return "oa"
        if h.startswith("eje"):
            return "eje"
        if "logro" in h or "correctas" in h or h in ("pct", "porcentaje"):
            return "pct"
        if "tipo" in h:
            return "tipo"
        if re.search(r"pregunta|item|reactivo", h) or re.fullmatch(r"n\s*°?\s*preg\w*", h):
            return "q"
    return None


def _extraer_questions(
    tablas: list[list[list[str]]], avisos: list[str]
) -> list[dict[str, Any]]:
    """Detalle por pregunta: OA, eje, habilidad, indicador, % y distribución.

    Recorre las tablas del PDF buscando las que tengan una columna de número
    de pregunta y una de indicador; el resto de columnas se resuelve por
    encabezado, de modo que un reordenamiento entre versiones no rompa nada.
    Una tabla que sigue en la página siguiente aparece como varias tablas con
    el encabezado repetido, así que las filas se acumulan y se deduplican por
    número de pregunta.
    """
    preguntas: list[dict[str, Any]] = []

    for tabla in tablas:
        if len(tabla) < 2:
            continue
        col: dict[str, int] = {}
        for j, celda in enumerate(tabla[0]):
            if (nombre := _clasificar_columna(celda or "")) is not None:
                col.setdefault(nombre, j)

        if "q" not in col or "ind" not in col:
            continue

        for fila in tabla[1:]:
            celdas = {k: (fila[j] if j < len(fila) else None) for k, j in col.items()}
            numero = _entero_celda(celdas.get("q"))
            indicador = limpiar(celdas.get("ind"))
            if numero is None or not indicador:
                continue

            dist = _distribucion(celdas)
            tipo = _tipo_item(limpiar(celdas.get("tipo")) or indicador, dist)
            # El logro se reconstruye desde la distribución, que trae dos
            # decimales, en vez de leer la columna «% Logro» ya redondeada.
            pct_col = _pct_celda(celdas.get("pct"))
            mostrado = logro_mostrado(tipo, dist) if dist else None
            if mostrado is None:
                mostrado = pct_col
            if mostrado is None:
                continue
            if pct_col is not None and dist and abs(pct_col - mostrado) > 1:
                avisos.append(
                    f"P{numero}: el PDF informa {pct_col:.0f}% de logro y su "
                    f"distribución de respuestas da {mostrado:.1f}%. Se usa la distribución."
                )
            # El puntaje con crédito parcial no se muestra por pregunta, pero
            # es lo que promedia el eje: sin él, Números y operaciones da
            # 75,6 % en vez del 76,4 % oficial. Sin distribución se cae al %
            # publicado, que es lo mejor disponible.
            puntaje = logro_puntaje(tipo, dist) if dist else mostrado

            try:
                eje = EJES[indice_eje(limpiar(celdas.get("eje")))]
            except KeyError:
                eje = ""

            preguntas.append(
                {
                    "q": numero,
                    "oa": _entero_celda(celdas.get("oa")) or 0,
                    "eje": eje,
                    "hab": limpiar(celdas.get("hab")),
                    # Redacción textual del informe oficial (guía §4).
                    "ind": indicador,
                    "pct": redondear_pct(mostrado),
                    "sem": semaforo(mostrado),
                    "puntaje_exacto": round(puntaje, 2),
                    "tipo": tipo,
                    "dist": dist,
                }
            )

    if not preguntas:
        raise ErrorParseo(
            FUENTE,
            "no se encontró la tabla de preguntas (se requieren al menos "
            "las columnas «N° pregunta» e «indicador»)",
        )

    unicas: dict[int, dict[str, Any]] = {}
    for pregunta in preguntas:
        if pregunta["q"] in unicas:
            avisos.append(f"P{pregunta['q']} aparece más de una vez en el PDF; se usa la primera")
            continue
        unicas[pregunta["q"]] = pregunta
    return [unicas[n] for n in sorted(unicas)]


# --- Punto de entrada -----------------------------------------------------


def parsear_dia_oficial(datos: bytes, nombre_archivo: str = "dia.pdf") -> ResultadoDia:
    """Lee el PDF oficial del DIA y devuelve su aporte al objeto `D`."""
    textos, tablas = _paginas(datos, nombre_archivo)
    texto = "\n".join(textos)

    resultado = ResultadoDia()
    resultado.meta = _extraer_meta(texto)
    resultado.niveles = _extraer_niveles(texto)
    resultado.eje_prom = _extraer_eje_prom(texto)
    resultado.questions = _extraer_questions(tablas, resultado.avisos)

    if not resultado.niveles or sum(resultado.niveles.values()) == 0:
        resultado.avisos.append(
            "no se leyeron los niveles de aprendizaje del PDF oficial; "
            "deben cargarse a mano (no se calculan con cortes de %)"
        )
    faltantes = [EJES[i] for i, p in enumerate(resultado.eje_prom) if p is None]
    if faltantes:
        resultado.avisos.append(
            "no se leyó el % por eje de: "
            + ", ".join(faltantes)
            + "; se calculará desde las preguntas"
        )
    return resultado
