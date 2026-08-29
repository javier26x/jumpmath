"""Ensamblado del objeto `D` a partir de los archivos de origen.

El módulo se llama `ensamblaje` y la función `ensamblar` para que
`jumpdia.ensamblar` no sea ambiguo: el paquete re-exporta la función, que si
coincidiera con el nombre del módulo lo sombrearía al importarlo.

Este módulo es el corazón del backend descrito en §4 de la guía: recibe los
bytes de cada archivo, los delega al parser correspondiente y aplica las
reglas de negocio para emitir el `D` que consume el HTML del informe.

No depende de Firebase ni de red: se puede ejecutar y testear en local.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .catalogo import EJE_CLAVES, EJES
from .errores import ErrorIngesta
from .normalizacion import clave, redondear_pct
from .parsers import (
    parsear_dia_oficial,
    parsear_estudiantes,
    parsear_plan_anual,
    parsear_recomendaciones,
    parsear_seguimiento,
)
from .parsers.plan_anual import nota_cobertura
from .reglas import (
    UMBRAL_DESCENDIDO,
    estado_recomendacion,
    etiqueta_unidades,
    global_estudiante,
    orden_recomendaciones,
    promedio_eje,
    promedio_global,
)
from .validacion import validar


@dataclass(slots=True)
class Archivo:
    """Un archivo subido por el usuario en el Paso 1."""

    nombre: str
    datos: bytes


@dataclass(slots=True)
class Entrada:
    """Los cinco archivos por curso (el plan anual es opcional)."""

    dia_oficial: Archivo
    estudiantes: Archivo
    recomendaciones: Archivo
    seguimiento: Archivo
    plan_anual: Archivo | None = None


@dataclass(slots=True)
class Salida:
    """`D` listo para el informe, más la traza de lo que hubo que asumir."""

    D: dict[str, Any]
    avisos: list[str] = field(default_factory=list)


#: Campos internos del parseo que no forman parte del contrato de `D` (§3).
_INTERNOS = ("puntaje_exacto",)


def _publicable(pregunta: dict[str, Any]) -> dict[str, Any]:
    """Deja una pregunta en la forma exacta que documenta el contrato.

    Se descartan el puntaje con crédito parcial —que sólo sirve para promediar
    el eje— y, dentro de `dist`, la marca de la alternativa correcta: el
    parser la deduce del destacado del PDF para calcular el logro, pero `dist`
    está documentada como la distribución de respuestas y el informe no la
    dibuja, así que no se le añaden claves.
    """
    limpia = {k: v for k, v in pregunta.items() if k not in _INTERNOS}
    limpia["dist"] = {k: v for k, v in pregunta["dist"].items() if k != "clave"}
    return limpia


def _preguntas_por_eje(questions: list[dict[str, Any]]) -> list[int]:
    """`D.ejeQC`: cuántas preguntas aporta cada eje (ponderación del global)."""
    return [sum(1 for q in questions if q["eje"] == eje) for eje in EJES]


def _promedios_por_eje(
    questions: list[dict[str, Any]], parseados: list[float | None], avisos: list[str]
) -> list[float]:
    """% por eje: se prefiere el valor oficial del PDF y se contrasta con el cálculo.

    Ambos deben coincidir; una divergencia mayor a medio punto indica que el
    PDF se leyó mal o que cambió la metodología, y se reporta sin bloquear.
    """
    proms: list[float] = []
    for i, eje in enumerate(EJES):
        puntajes = [q["puntaje_exacto"] for q in questions if q["eje"] == eje]
        calculado = promedio_eje(puntajes)
        oficial = parseados[i] if i < len(parseados) else None

        if oficial is None:
            proms.append(calculado)
            continue
        if puntajes and abs(oficial - calculado) > 0.5:
            avisos.append(
                f"«{eje}»: el PDF informa {oficial:.1f}% y las preguntas dan "
                f"{calculado:.1f}%. Se usa el valor oficial del PDF."
            )
        proms.append(round(oficial, 1))
    return proms


def _armar_students(
    crudos: list[dict[str, Any]], eje_qc: list[int], avisos: list[str]
) -> list[dict[str, Any]]:
    """Normaliza la nómina y calcula el global de cada estudiante."""
    aproximados = 0
    students: list[dict[str, Any]] = []

    for alumno in crudos:
        pcts = [float(alumno[k]) for k in EJE_CLAVES]
        crudo = alumno.get("puntaje_crudo")
        # Ponderar los % por eje da el global exacto mientras lleguen sin
        # redondear. Sólo si el archivo ya trae enteros —y no hay puntaje
        # crudo— el resultado puede desviarse, y entonces se avisa.
        if crudo is None and all(float(p).is_integer() for p in pcts):
            aproximados += 1
        g = global_estudiante(pcts, eje_qc, crudo)

        informado = alumno.get("g_informado")
        if informado is not None and abs(informado - g) > 1:
            avisos.append(
                f"{alumno['n']}: el archivo informa {informado:.0f}% global y el "
                f"cálculo da {g}%. Se usa el calculado."
            )

        students.append(
            {
                "n": alumno["n"],
                **{k: redondear_pct(alumno[k]) for k in EJE_CLAVES},
                "g": g,
                "lv": alumno["lv"],
            }
        )

    if aproximados:
        avisos.append(
            f"{aproximados} de {len(crudos)} estudiantes traen sus % por eje ya "
            "redondeados y sin puntaje crudo: su global se pondera desde esos "
            "enteros y puede desviarse un punto. Incluya la columna de aciertos "
            "para un cálculo exacto."
        )
    return students


def _armar_recs(
    questions: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    rec,
    avisos: list[str],
) -> list[dict[str, Any]]:
    """Recomendaciones para todo indicador descendido (<80 %), del peor al mejor.

    El cruce con la planilla se hace por **N° de pregunta**, que ambas fuentes
    comparten. Emparejar por el texto del indicador sólo se usa como respaldo:
    basta una coma o una tilde de diferencia para perder la coincidencia.
    """
    por_clave = {f"{c['tomo']}/{c['u']}": c for c in coverage}
    recs: list[dict[str, Any]] = []

    for q in questions:
        if q["pct"] >= UMBRAL_DESCENDIDO:
            continue

        numero, llave = q["q"], clave(q["ind"])
        unidades = rec.unidades.get(numero) or rec.unidades_por_indicador.get(llave, [])
        base = rec.base.get(numero) or rec.base_por_indicador.get(llave, "")
        plus = rec.plus.get(numero) or rec.plus_por_indicador.get(llave, "")

        if not unidades:
            avisos.append(
                f"P{numero} «{q['ind'][:55]}…»: sin unidad JUMP asociada en la "
                "planilla de recomendaciones; queda como 'esperado' y sin unidades."
            )
        if not base:
            avisos.append(
                f"P{numero} «{q['ind'][:55]}…»: sin texto de recomendación en la planilla."
            )

        detalle = [por_clave[u.clave] for u in unidades if u.clave in por_clave]
        recs.append(
            {
                "q": numero,
                "oa": str(q["oa"]),
                "ind": q["ind"],
                "pct": q["pct"],
                "sem": q["sem"],
                "units": etiqueta_unidades(detalle),
                "estado": estado_recomendacion([c["status"] == "res" for c in detalle]),
                "base": base,
                "plus": plus,
            }
        )

    recs.sort(key=orden_recomendaciones)
    return recs


def ensamblar(entrada: Entrada, *, estricto: bool = True) -> Salida:
    """Ejecuta el pipeline completo: archivos → objeto `D` validado.

    Con `estricto=False` la validación reporta los problemas como avisos en
    vez de abortar, lo que permite previsualizar un informe incompleto.
    """
    avisos: list[str] = []

    dia = parsear_dia_oficial(entrada.dia_oficial.datos, entrada.dia_oficial.nombre)
    est = parsear_estudiantes(entrada.estudiantes.datos, entrada.estudiantes.nombre)
    rec = parsear_recomendaciones(entrada.recomendaciones.datos, entrada.recomendaciones.nombre)
    seg = parsear_seguimiento(entrada.seguimiento.datos, entrada.seguimiento.nombre)
    plan = (
        parsear_plan_anual(entrada.plan_anual.datos, entrada.plan_anual.nombre)
        if entrada.plan_anual
        else None
    )

    for parcial in (dia, est, rec, seg, plan):
        if parcial is not None:
            avisos.extend(parcial.avisos)

    questions = dia.questions
    eje_qc = _preguntas_por_eje(questions)
    eje_prom = _promedios_por_eje(questions, dia.eje_prom, avisos)
    students = _armar_students(est.students, eje_qc, avisos)

    sin_eje = [q["q"] for q in questions if not q["eje"]]
    if sin_eje:
        avisos.append(
            "preguntas sin eje reconocido (no ponderan en el global): "
            + ", ".join(f"P{n}" for n in sin_eje)
        )

    # El nivel de cada estudiante es el que asigna la Agencia y llega en la
    # nómina oficial; contarlos no es recalcularlos con cortes de porcentaje,
    # que es lo que la guía prohíbe. Se usa el recuento del PDF cuando existe,
    # pero el Gráfico 1 no trae capa de texto y casi nunca es legible.
    conteo = {"I": 0, "II": 0, "III": 0}
    for alumno in students:
        conteo[("I", "II", "III")[alumno["lv"] - 1]] += 1

    niveles = dict(dia.niveles) if dia.niveles else conteo
    if dia.niveles and niveles != conteo:
        avisos.append(
            f"los niveles del PDF oficial {niveles} no coinciden con el conteo de la "
            f"nómina {conteo}. Se usan los del PDF oficial (guía §4)."
        )

    if (n_pdf := dia.meta.get("n")) is not None and n_pdf != len(students):
        avisos.append(
            f"el PDF declara {n_pdf} estudiantes y la nómina trae {len(students)}. "
            "Se usa la nómina, que es la que alimenta el informe por estudiante."
        )

    meta = {
        "colegio": dia.meta.get("colegio", ""),
        "rbd": dia.meta.get("rbd", ""),
        "curso": dia.meta.get("curso", ""),
        "docente": dia.meta.get("docente", ""),
        "director": dia.meta.get("director", ""),
        "n": len(students),
        "fecha": dia.meta.get("fecha", ""),
        "prueba": dia.meta.get("prueba", "DIA · Matemática"),
    }

    D: dict[str, Any] = {
        "meta": meta,
        "niveles": niveles,
        "ejes": list(EJES),
        "ejeProm": eje_prom,
        "promGlobal": promedio_global(eje_prom, eje_qc),
        "students": students,
        "questions": [_publicable(q) for q in questions],
        "coverage": seg.coverage,
        "recs": _armar_recs(questions, seg.coverage, rec, avisos),
        "ejeQC": eje_qc,
    }

    if plan and plan.secuencia:
        D["notaCobertura"] = nota_cobertura(plan.secuencia, seg.coverage)

    problemas = validar(D)
    if problemas:
        if estricto:
            from .errores import ErrorValidacion

            raise ErrorValidacion(problemas)
        avisos.extend(problemas)

    return Salida(D=D, avisos=avisos)


__all__ = ["Archivo", "Entrada", "ErrorIngesta", "Salida", "ensamblar"]
