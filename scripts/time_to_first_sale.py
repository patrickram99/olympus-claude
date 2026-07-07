#!/usr/bin/env python3
"""
Días entre FechaIngreso y primera matriculación atribuida al asesor.

Por defecto usa "sales mode": como los datos de ventas en el CRM sólo se
registran desde SALES_DATA_START (2026-01-01 por defecto, configurable en
.env), la `FechaIngreso` se trunca a `MAX(FechaIngreso, SALES_DATA_START)`.
Esto evita que el 48% de asesores con `FechaIngreso` pre-CRM (2005-2025)
salgan con DiferenciaDias = 7,000+ días.

Para análisis HR/rotación pasale `--hr-mode` y se respeta la `FechaIngreso`
real.

Uso:
  python scripts/time_to_first_sale.py                            # sales mode, todos
  python scripts/time_to_first_sale.py --since 2026-03-01         # solo cohorte de marzo+
  python scripts/time_to_first_sale.py --excluir-outliers 90      # ajustar umbral outlier
  python scripts/time_to_first_sale.py --hr-mode --since 2025-01-01  # análisis HR
  python scripts/time_to_first_sale.py -o asesores_ttfs.csv
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="Time to first sale por asesor")
    ap.add_argument("--since", default="2000-01-01", help="Filtrar FechaIngreso efectiva >= esta fecha (YYYY-MM-DD). Default: sin filtro.")
    ap.add_argument("--excluir-outliers", type=int, default=365, help="Excluir DiferenciaDias > N (default 365). 0 para incluir todo.")
    ap.add_argument("--hr-mode", action="store_true", help="Usar FechaIngreso real (para análisis de rotación/HR). Default: sales mode = MAX(FechaIngreso, SALES_DATA_START).")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    sql = queries.sql_time_to_first_sale(hr_mode=args.hr_mode)
    rows = db.query(sql, [args.since])

    if args.excluir_outliers > 0:
        rows = [r for r in rows if r["DiferenciaDias"] <= args.excluir_outliers]

    rows.sort(key=lambda r: r["DiferenciaDias"])

    modo = "HR (FechaIngreso real)" if args.hr_mode else f"sales (cap={queries.SALES_DATA_START})"
    if rows:
        dias = [r["DiferenciaDias"] for r in rows]
        prom = sum(dias) / len(dias)
        med = statistics.median(dias)
        print(
            f"\n>>> Modo: {modo} · N={len(rows)} · Promedio={prom:.1f}d · "
            f"Mediana={med}d · Min={min(dias)} · Max={max(dias)}\n",
            file=sys.stderr,
        )
    else:
        print(f"\n>>> Modo: {modo} · N=0\n", file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
