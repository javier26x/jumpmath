"""Reglas de negocio del informe DIA (guía del desarrollador, §4).

Cada función implementa una regla explícita de la guía. Están aisladas del
parseo a propósito: los parsers extraen datos crudos y estas reglas deciden
qué significa cada número. Los tests las contrastan contra el informe 4° A
publicado, que actúa como referencia dorada.
"""

from __future__ import annotations

from .catalogo import TIPOS_ITEM
from .normalizacion import redondear_pct

# --- Semáforo -------------------------------------------------------------

UMBRAL_VERDE = 80.0
UMBRAL_AMARILLO = 60.0


def semaforo(pct: float | int | None) -> str:
    """Color de logro: ``V`` ≥80 % · ``A`` 60–79 % · ``R`` <60 %.

    Se evalúa sobre el porcentaje **ya redondeado** que muestra el informe,
    de modo que un 79,6 % se lea como el 80 % verde que ve el usuario y no
    exista un ítem pintado de amarillo con un «80 %» al lado.
    """
    if pct is None:
        return "N"
    entero = redondear_pct(float(pct))
    if entero >= UMBRAL_VERDE:
        return "V"
    if entero >= UMBRAL_AMARILLO:
        return "A"
    return "R"


# --- Logro por pregunta ---------------------------------------------------


def _clave_correcta(dist: dict[str, float]) -> float:
    """% de la alternativa correcta en un ítem de selección múltiple.

    Cuando el parser no pudo marcar la clave se toma la alternativa más
    elegida, distinta de la omisión: en un ítem con logro mayoritario es la
    clave, y en uno muy descendido el valor queda explícito en `dist` para
    que el docente lo revise en la tabla de distractores.
    """
    opciones = {k: v for k, v in dist.items() if k not in ("N", "clave")}
    if not opciones:
        return 0.0
    marcada = dist.get("clave")
    if isinstance(marcada, str) and marcada in opciones:
        return opciones[marcada]
    return max(opciones.values())


def logro_mostrado(tipo: str, dist: dict[str, float]) -> float:  # noqa: ARG001
    """% de logro **del ítem**, tal como lo publica el informe.

    Recibe `tipo` sin usarlo, para que sea intercambiable con `logro_puntaje`:
    quien calcula ambas magnitudes las llama con los mismos argumentos.

    Cuenta sólo la respuesta completamente correcta. En un ítem de desarrollo
    la respuesta parcialmente correcta **no** suma aquí: la P5 de 4° A se
    publica como 38 % (`RC`) aunque un 23 % adicional respondió parcialmente
    bien. Ese matiz se muestra aparte, en la distribución de respuestas.
    """
    if "RC" in dist:
        return dist.get("RC", 0.0)
    return _clave_correcta(dist)


def logro_puntaje(tipo: str, dist: dict[str, float]) -> float:
    """% de **puntaje** del ítem, con crédito parcial. Base del promedio por eje.

    La Agencia puntúa con medio punto la respuesta parcialmente correcta, así
    que el promedio del eje no se calcula con `logro_mostrado`: en 4° A, contar
    la P5 como 38 % en vez de 50 % baja Números y operaciones de 76,4 % —el
    valor oficial— a 75,6 %.
    """
    if tipo == TIPOS_ITEM[2]:  # desarrollo
        return dist.get("RC", 0.0) + 0.5 * dist.get("RPC", 0.0)
    if "RC" in dist:
        return dist.get("RC", 0.0)
    return _clave_correcta(dist)


# --- Agregados por eje y global ------------------------------------------


def promedio_eje(puntajes: list[float]) -> float:
    """Promedio simple de los ítems del eje, a un decimal (como el DIA).

    Recibe `logro_puntaje` de cada ítem, no `logro_mostrado`.
    """
    if not puntajes:
        return 0.0
    return round(sum(puntajes) / len(puntajes), 1)


def promedio_global(prom_por_eje: list[float], preguntas_por_eje: list[int]) -> int:
    """% global del curso: promedio **ponderado por N° de preguntas del eje**.

    No es el promedio simple de las cinco columnas: Números y operaciones
    aporta 15 de 31 preguntas y debe pesar como tal (guía §4).
    """
    total = sum(preguntas_por_eje)
    if total == 0:
        return 0
    acum = sum(p * c for p, c in zip(prom_por_eje, preguntas_por_eje, strict=True))
    return redondear_pct(acum / total)


def global_estudiante(
    pct_por_eje: list[float],
    preguntas_por_eje: list[int],
    puntaje_crudo: float | None = None,
) -> int:
    """% global de un estudiante sobre las 31 preguntas.

    Con `puntaje_crudo` (aciertos, medio punto en ítems de desarrollo) el
    cálculo es exacto. Sin él se pondera por N° de preguntas del eje, que es
    equivalente **sólo si los porcentajes por eje vienen sin redondear**: con
    los enteros del informe, tres de los 26 estudiantes de 4° A se desvían en
    un punto. `ensamblar` avisa cuando cae en este modo aproximado.
    """
    total = sum(preguntas_por_eje)
    if total == 0:
        return 0
    if puntaje_crudo is not None:
        return redondear_pct(100.0 * puntaje_crudo / total)
    acum = sum(p * c for p, c in zip(pct_por_eje, preguntas_por_eje, strict=True))
    return redondear_pct(acum / total)


# --- Cobertura JUMP y recomendaciones ------------------------------------


def estado_recomendacion(unidades_trabajadas: list[bool]) -> str:
    """``remediar`` si alguna unidad JUMP del indicador ya se trabajó.

    Un indicador descendido cuyo contenido ya se pasó es prioridad de
    remediación; si aún no se aborda, sólo hay que secuenciarlo bien.
    """
    return "remediar" if any(unidades_trabajadas) else "esperado"


def etiqueta_unidades(unidades: list[dict]) -> str:
    """Texto de `recs[].units`: ``"4.1 · U2 Valor posicional… ✓ 85% · …"``.

    ``✓ n%`` cuando hay control o prueba registrada; ``✗`` cuando no hay
    registro — lo que **no** significa "no trabajada" (guía §4).
    """
    partes = []
    for u in unidades:
        marca = f"✓ {redondear_pct(u['pct'])}%" if u.get("status") == "res" else "✗"
        partes.append(f"{u['tomo']} · {u['u']} {u['label']} {marca}")
    return " · ".join(partes)


def orden_recomendaciones(rec: dict) -> tuple[float, int]:
    """Orden del listado: primero el logro más bajo; empate por N° de pregunta."""
    return (rec["pct"], rec["q"])


#: Umbral bajo el cual un indicador entra al listado de recomendaciones.
UMBRAL_DESCENDIDO = 80
