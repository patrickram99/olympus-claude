#!/usr/bin/env python3
"""
Estado ACTUAL del funnel: foto del stock de oportunidades por etapa vigente.

A diferencia de funnel_transitions.py (que mide el FLUJO entre etapas en una
ventana), esto cuenta en qué estado está HOY cada oportunidad — la última fila
de HistorialEstado por oportunidad. Útil para ver dónde está atascado el
pipeline de un curso (cuántos leads vivos en Calificado/Potencial/Promesa vs.
ya matriculados o perdidos).

Uso:
  python scripts/funnel_estado.py                 # global (todos los productos)
  python scripts/funnel_estado.py 400             # un producto
  python scripts/funnel_estado.py 400 -o funnel.csv --fmt csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output

# Orden de presentación del funnel: progresión activa, luego cierres.
ESTADOS = [
    (1, "Registrado", "activo"),
    (4, "Calificado", "activo"),
    (5, "Potencial", "activo"),
    (6, "Promesa", "activo"),
    (3, "Matriculado", "ganado"),
    (7, "Perdido", "perdido"),
    (2, "No calificado", "descartado"),
]
NOMBRE = {e: n for e, n, _ in ESTADOS}
GRUPO = {e: g for e, _, g in ESTADOS}


def main():
    ap = argparse.ArgumentParser(description="Estado actual del funnel de un producto")
    ap.add_argument("producto", type=int, nargs="?", default=None,
                    help="IdProducto. Omitir para global.")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    rows = db.query(queries.SQL_FUNNEL_ESTADO_ACTUAL, [args.producto, args.producto])
    counts = {int(r["IdEstado"]): int(r["N"]) for r in rows}
    total = sum(counts.values())

    result = []
    for estado, nombre, grupo in ESTADOS:
        n = counts.get(estado, 0)
        result.append({
            "Estado": nombre,
            "Grupo": grupo,
            "Oportunidades": n,
            "% del total": round(n / total * 100, 2) if total else None,
        })
    # Estados inesperados (fuera del catálogo conocido) para no perder filas.
    for estado, n in counts.items():
        if estado not in NOMBRE:
            result.append({
                "Estado": f"(estado {estado})",
                "Grupo": "?",
                "Oportunidades": n,
                "% del total": round(n / total * 100, 2) if total else None,
            })

    activos = sum(n for e, n in counts.items() if GRUPO.get(e) == "activo")
    ganados = counts.get(3, 0)
    cerrados_neg = sum(counts.get(e, 0) for e in (7, 2))

    scope = f"producto {args.producto}" if args.producto else "GLOBAL"
    print(f"\n>>> ESTADO ACTUAL DEL FUNNEL · {scope}", file=sys.stderr)
    print(f">>> Total oportunidades: {total:,}  ·  Activas (1/4/5/6): {activos:,}"
          f"  ·  Matriculadas: {ganados:,}  ·  Perdidas/Descartadas: {cerrados_neg:,}",
          file=sys.stderr)
    if total:
        print(f">>> TC actual (matriculadas/total): {ganados / total * 100:.2f}%\n",
              file=sys.stderr)
    else:
        print("", file=sys.stderr)

    output(result, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
