#!/usr/bin/env python3
"""
Ranking de países por eficiencia (TC + Wilson LB) para un set de productos.

Uso:
  python scripts/paises_priority.py                            # todos los productos
  python scripts/paises_priority.py --tema "mantenimiento"     # filtro Producto.Nombre LIKE
  python scripts/paises_priority.py --tema "finanzas|financ"   # multiple LIKE patterns
  python scripts/paises_priority.py -o paises.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.calc import wilson_lb
from lib.format import output


def collect_for_pattern(pattern: str) -> tuple[dict, dict]:
    leads = {r["Pais"]: int(r["Leads"]) for r in db.query(queries.SQL_LEADS_POR_PAIS, [f"%{pattern}%"])}
    matric = {r["Pais"]: int(r["Matriculados"]) for r in db.query(queries.SQL_MATRIC_POR_PAIS, [f"%{pattern}%"])}
    return leads, matric


def main():
    ap = argparse.ArgumentParser(description="Priorización de países por Wilson LB")
    ap.add_argument("--tema", default="", help="Patrones LIKE separados por |. Vacío = todos los productos.")
    ap.add_argument("--min-leads", type=int, default=0, help="Excluir países con menos de N leads")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    if args.tema:
        patterns = [p.strip() for p in args.tema.split("|") if p.strip()]
    else:
        patterns = [""]  # matches everything

    total_leads: dict[str, int] = {}
    total_matric: dict[str, int] = {}
    for pat in patterns:
        l, m = collect_for_pattern(pat)
        for k, v in l.items(): total_leads[k] = total_leads.get(k, 0) + v
        for k, v in m.items(): total_matric[k] = total_matric.get(k, 0) + v

    rows = []
    for pais in sorted(set(total_leads) | set(total_matric)):
        l = total_leads.get(pais, 0)
        m = total_matric.get(pais, 0)
        if l < args.min_leads:
            continue
        tc = (m / l) if l else 0
        w = wilson_lb(m, l)
        rows.append({
            "Pais": pais,
            "Leads": l,
            "Matric": m,
            "TC%": round(tc * 100, 3),
            "WilsonLB%": round(w * 100, 3),
        })

    rows.sort(key=lambda r: -r["WilsonLB%"])
    print(f"\n>>> Tema(s): {patterns} · {len(rows)} países\n", file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
