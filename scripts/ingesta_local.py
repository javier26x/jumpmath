#!/usr/bin/env python3
"""Ejecuta la ingesta en local, sin Firebase.

Sirve para dos cosas: depurar la planilla de un colegio nuevo viendo el
diagnóstico completo, y generar el informe de un curso sin desplegar nada.

    python scripts/ingesta_local.py \
        --dia        informe_DIA_4A.pdf \
        --estudiantes resultados_estudiantes.pdf \
        --recomendaciones "Recomendaciones por indicador 4° BP.xlsx" \
        --seguimiento seguimiento_jump.xlsx \
        [--plan-anual plan_anual.xlsx] \
        [--salida informe_4A.html] [--json D_4A.json] [--permisivo]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "functions"))

from jumpdia import Archivo, Entrada, ErrorIngesta, ensamblar, preparar_informe  # noqa: E402

PLANTILLA = RAIZ / "public" / "index.html"


def _archivo(ruta: str | None) -> Archivo | None:
    if not ruta:
        return None
    p = pathlib.Path(ruta)
    if not p.is_file():
        raise SystemExit(f"No existe el archivo: {p}")
    return Archivo(nombre=p.name, datos=p.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dia", required=True, help="informe oficial DIA (PDF)")
    parser.add_argument(
        "--estudiantes", required=True, help="resultados por estudiante (PDF o xlsx)"
    )
    parser.add_argument(
        "--recomendaciones", required=True, help="recomendaciones por indicador (xlsx)"
    )
    parser.add_argument(
        "--seguimiento", required=True, help="seguimiento de evaluaciones JUMP (xlsx)"
    )
    parser.add_argument("--plan-anual", help="plan anual del curso (opcional)")
    parser.add_argument("--salida", type=pathlib.Path, help="ruta del HTML a escribir")
    parser.add_argument("--json", type=pathlib.Path, help="ruta del objeto D a escribir")
    parser.add_argument(
        "--permisivo",
        action="store_true",
        help="no aborta si D incumple el contrato; reporta los problemas como avisos",
    )
    args = parser.parse_args(argv)

    try:
        salida = ensamblar(
            Entrada(
                dia_oficial=_archivo(args.dia),
                estudiantes=_archivo(args.estudiantes),
                recomendaciones=_archivo(args.recomendaciones),
                seguimiento=_archivo(args.seguimiento),
                plan_anual=_archivo(args.plan_anual),
            ),
            estricto=not args.permisivo,
        )
    except ErrorIngesta as exc:
        print(f"\nLa ingesta falló:\n{exc}\n", file=sys.stderr)
        return 1

    meta = salida.D["meta"]
    print(f"\n{meta['colegio']} · {meta['curso']} · {meta['prueba']}")
    print(f"  {meta['n']} estudiantes · logro global {salida.D['promGlobal']}%")
    print(f"  niveles: {salida.D['niveles']}")
    print(
        f"  {len(salida.D['questions'])} preguntas · "
        f"{len(salida.D['recs'])} indicadores descendidos"
    )

    if salida.avisos:
        print(f"\n{len(salida.avisos)} aviso(s):")
        for aviso in salida.avisos:
            print(f"  · {aviso}")

    if args.json:
        args.json.write_text(
            json.dumps(salida.D, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nD escrito en {args.json}")
    if args.salida:
        html = preparar_informe(PLANTILLA.read_text(encoding="utf-8"), salida.D)
        args.salida.write_text(html, encoding="utf-8")
        print(f"Informe escrito en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
