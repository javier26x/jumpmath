"""Validación del objeto `D` contra el contrato de datos (guía §3 y §4).

Devuelve una lista de problemas legibles en vez de lanzar en el primer error:
quien corrige una planilla necesita ver todo lo que está mal de una vez.
"""

from __future__ import annotations

from typing import Any

from .catalogo import EJE_CLAVES, EJES, TIPOS_ITEM, UNIDADES_JUMP
from .reglas import UMBRAL_DESCENDIDO, promedio_global, semaforo

_CLAVES_D = (
    "meta", "niveles", "ejes", "ejeProm", "promGlobal",
    "students", "questions", "coverage", "recs", "ejeQC",
)
_CLAVES_META = ("colegio", "rbd", "curso", "docente", "director", "n", "fecha", "prueba")


def _pct_valido(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100


def validar(D: dict[str, Any]) -> list[str]:
    """Comprueba estructura, rangos y coherencia interna de `D`."""
    p: list[str] = []

    if faltan := [k for k in _CLAVES_D if k not in D]:
        return [f"faltan claves obligatorias en D: {', '.join(faltan)}"]

    # --- meta -------------------------------------------------------------
    meta = D["meta"]
    for k in _CLAVES_META:
        if k not in meta:
            p.append(f"meta.{k} ausente")
        elif k != "n" and not str(meta[k]).strip():
            p.append(f"meta.{k} vacío")
    if meta.get("n") != len(D["students"]):
        p.append(f"meta.n={meta.get('n')} no coincide con {len(D['students'])} estudiantes")

    # --- ejes y ponderación ----------------------------------------------
    if D["ejes"] != list(EJES):
        p.append(f"D.ejes no coincide con el catálogo canónico: {D['ejes']}")
    for nombre, largo in (("ejeProm", len(D["ejeProm"])), ("ejeQC", len(D["ejeQC"]))):
        if largo != len(EJES):
            p.append(f"D.{nombre} debe tener {len(EJES)} elementos, tiene {largo}")
    if any(not _pct_valido(v) for v in D["ejeProm"]):
        p.append(f"D.ejeProm fuera de rango 0–100: {D['ejeProm']}")

    total_q = sum(D["ejeQC"])
    con_eje = sum(1 for q in D["questions"] if q["eje"])
    if total_q != con_eje:
        p.append(f"D.ejeQC suma {total_q} pero hay {con_eje} preguntas con eje asignado")

    # Sólo tiene sentido comprobar el global si los dos vectores están completos;
    # con largos distintos el problema ya se reportó y ponderar lanzaría.
    if len(D["ejeProm"]) == len(D["ejeQC"]) == len(EJES):
        esperado = promedio_global(D["ejeProm"], D["ejeQC"])
        if D["promGlobal"] != esperado:
            p.append(
                f"D.promGlobal={D['promGlobal']} no es el ponderado por N° de preguntas "
                f"({esperado}). Regla: promedio de ejes ponderado por ejeQC."
            )

    # --- niveles ----------------------------------------------------------
    niveles = D["niveles"]
    if faltan := [r for r in ("I", "II", "III") if r not in niveles]:
        p.append(f"D.niveles sin los tres niveles oficiales: faltan {', '.join(faltan)}")
    elif sum(niveles.values()) != len(D["students"]):
        p.append(
            f"D.niveles suma {sum(niveles.values())} estudiantes pero la nómina "
            f"tiene {len(D['students'])}"
        )

    # --- estudiantes ------------------------------------------------------
    vistos: set[str] = set()
    for s in D["students"]:
        if not str(s.get("n", "")).strip():
            p.append("hay un estudiante sin nombre")
        elif s["n"] in vistos:
            p.append(f"estudiante duplicado: {s['n']}")
        else:
            vistos.add(s["n"])
        for k in (*EJE_CLAVES, "g"):
            if not _pct_valido(s.get(k)):
                p.append(f"{s.get('n', '?')}: {k}={s.get(k)!r} no es un % válido")
        if s.get("lv") not in (1, 2, 3):
            p.append(f"{s.get('n', '?')}: lv={s.get('lv')!r} no es un nivel DIA (1|2|3)")

    # --- preguntas --------------------------------------------------------
    numeros = [q.get("q") for q in D["questions"]]
    if len(set(numeros)) != len(numeros):
        p.append("hay números de pregunta repetidos en D.questions")
    for q in D["questions"]:
        if not _pct_valido(q.get("pct")):
            p.append(f"P{q.get('q')}: pct={q.get('pct')!r} no es un % válido")
        elif q.get("sem") != semaforo(q["pct"]):
            p.append(
                f"P{q.get('q')}: sem={q.get('sem')!r} no corresponde a {q['pct']}% "
                "(V ≥80 · A 60–79 · R <60)"
            )
        if not str(q.get("ind", "")).strip():
            p.append(f"P{q.get('q')}: indicador vacío")
        if q.get("tipo") not in TIPOS_ITEM:
            p.append(f"P{q.get('q')}: tipo={q.get('tipo')!r} desconocido")

    # --- cobertura --------------------------------------------------------
    if len(D["coverage"]) != len(UNIDADES_JUMP):
        p.append(
            f"D.coverage debe listar las {len(UNIDADES_JUMP)} unidades JUMP, "
            f"tiene {len(D['coverage'])}"
        )
    for c in D["coverage"]:
        if c.get("status") not in ("res", "none"):
            p.append(
                f"{c.get('tomo')}·{c.get('u')}: status={c.get('status')!r} debe ser 'res'|'none'"
            )
        if c.get("status") == "res" and not _pct_valido(c.get("pct")):
            p.append(f"{c.get('tomo')}·{c.get('u')}: status 'res' exige un pct válido")
        if c.get("status") == "none" and c.get("pct") is not None:
            p.append(f"{c.get('tomo')}·{c.get('u')}: status 'none' no debe traer pct")

    # --- recomendaciones --------------------------------------------------
    descendidos = {
        q["q"]
        for q in D["questions"]
        if _pct_valido(q.get("pct")) and q["pct"] < UMBRAL_DESCENDIDO
    }
    en_recs = {r.get("q") for r in D["recs"]}
    if faltan_recs := descendidos - en_recs:
        p.append(
            "indicadores descendidos sin recomendación: "
            + ", ".join(f"P{n}" for n in sorted(faltan_recs))
        )
    if sobran := en_recs - descendidos:
        p.append(
            "recomendaciones para indicadores no descendidos (≥80 %): "
            + ", ".join(f"P{n}" for n in sorted(sobran))
        )
    orden = [(r.get("pct"), r.get("q")) for r in D["recs"]]
    if orden != sorted(orden):
        p.append("D.recs no está ordenado por % de logro ascendente (empate por N° de pregunta)")
    for r in D["recs"]:
        if r.get("estado") not in ("remediar", "esperado"):
            p.append(f"P{r.get('q')}: estado={r.get('estado')!r} debe ser 'remediar'|'esperado'")
        elif (r["estado"] == "remediar") != ("✓" in str(r.get("units", ""))):
            p.append(
                f"P{r.get('q')}: estado='{r['estado']}' no concuerda con units="
                f"{r.get('units')!r} ('remediar' exige una unidad ya trabajada)"
            )

    return p
