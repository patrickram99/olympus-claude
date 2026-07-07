#!/usr/bin/env python3
"""
Distribución de llamadas por hora del día (0-23) con % contestadas.

Uso:
  python scripts/calls_by_hour.py [--periodo 30] [-o out.csv]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="Llamadas por hora del día")
    ap.add_argument("--periodo", type=int, default=30)
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    rows = db.query(queries.SQL_CALLS_BY_HOUR, [args.periodo])
    rows.sort(key=lambda r: r["Hora"])

    # Identificar mejor franja (con volumen ≥ 5% del pico)
    max_vol = max((int(r["Total"]) for r in rows), default=0)
    threshold = max_vol * 0.05
    enrich = []
    for r in rows:
        tot = int(r["Total"] or 0)
        cc = int(r["Contestadas"] or 0)
        pct = (cc / tot) if tot else 0
        enrich.append({
            "Hora": f"{int(r['Hora']):02d}:00",
            "Contestadas": cc,
            "NoContestadas": int(r["NoContestadas"] or 0),
            "Total": tot,
            "%Contestadas": round(pct * 100, 2),
            "Elegible": tot >= threshold,
        })

    elig = [r for r in enrich if r["Elegible"]]
    if elig:
        best = max(elig, key=lambda r: r["%Contestadas"])
        print(f"\n>>> Período: {args.periodo} días · mejor franja: {best['Hora']} → {best['%Contestadas']}% sobre {best['Total']:,} llamadas\n", file=sys.stderr)
    output(enrich, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
