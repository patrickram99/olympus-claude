#!/usr/bin/env python3
"""
Matriz de transiciones por etapa del pipeline (global o por asesor).

Uso:
  python scripts/funnel_transitions.py                    # global
  python scripts/funnel_transitions.py --asesor 81        # un asesor
  python scripts/funnel_transitions.py --periodo 90 -o funnel.csv
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output

ESTADOS = {1: "Reg", 4: "Cal", 5: "Pot", 6: "Prom", 3: "Mat", 7: "Perd"}
PASOS = [
    ("Reg→Cal+", 1, {4, 5, 6, 3}),
    ("Cal→Pot+", 4, {5, 6, 3}),
    ("Pot→Prom+", 5, {6, 3}),
    ("Prom→Mat", 6, {3}),
]


def main():
    ap = argparse.ArgumentParser(description="Matriz de transiciones")
    ap.add_argument("--periodo", type=int, default=90)
    ap.add_argument("--asesor", type=int, help="Filtrar a un IdPersonal específico")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    rows = db.query(queries.SQL_TRANSICIONES, [args.periodo])
    if args.asesor:
        rows = [r for r in rows if r["IdPersonal"] == args.asesor]

    counts = defaultdict(int)
    for r in rows:
        counts[(int(r["EstadoOrigen"]), int(r["EstadoDestino"]))] += int(r["N"])

    result = []
    for label, origen, avance in PASOS:
        tot = sum(n for (o, d), n in counts.items() if o == origen)
        av = sum(n for (o, d), n in counts.items() if o == origen and d in avance)
        pct = (av / tot) if tot else None
        result.append({
            "Etapa": label,
            "Avanzan": av,
            "Total_desde_origen": tot,
            "% avance": round(pct * 100, 2) if pct is not None else None,
        })

    if args.asesor:
        print(f"\n>>> Asesor {args.asesor} · período {args.periodo}d\n", file=sys.stderr)
    else:
        print(f"\n>>> GLOBAL · período {args.periodo}d\n", file=sys.stderr)
    output(result, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
