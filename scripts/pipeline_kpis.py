#!/usr/bin/env python3
"""
Pipeline KPIs — snapshot global del CRM (asesores activos, llamadas, leads, matrículas, TC, tiempo a primer contacto).

Uso:
  python scripts/pipeline_kpis.py [--periodo 30] [--jornada 31|32] [-o out.csv] [--fmt table|csv|json]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output, fmt_pct


def main():
    ap = argparse.ArgumentParser(description="Snapshot global de KPIs del pipeline")
    ap.add_argument("--periodo", type=int, default=30, help="Días hacia atrás (default 30)")
    ap.add_argument("--jornada", type=int, choices=[31, 32], help="Filtrar por jornada (31=TC, 32=TP)")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    args = ap.parse_args()

    p = args.periodo

    llamadas = {r["IdPersonal"]: r for r in db.query(queries.SQL_LLAMADAS_POR_ASESOR, [p])}
    leads = {r["IdPersonal"]: r["LeadsAsignados"] for r in db.query(queries.SQL_LEADS_ASIGNADOS, [p])}
    matric = {r["IdPersonal"]: r["Matriculas"] for r in db.query(queries.SQL_MATRICULAS_POR_ASESOR, [p])}
    asesores = db.query(queries.SQL_ASESORES_ACTIVOS)

    if args.jornada:
        asesores = [a for a in asesores if a["Jornada"] == args.jornada]
    allowed = {a["Id"] for a in asesores}

    total_c = sum(r["Contestadas"] for k, r in llamadas.items() if k in allowed)
    total_n = sum(r["NoContestadas"] for k, r in llamadas.items() if k in allowed)
    total_l = sum(v for k, v in leads.items() if k in allowed)
    total_m = sum(v for k, v in matric.items() if k in allowed)
    activos = len({k for k in (set(llamadas) | set(leads)) if k in allowed})

    # Tiempo a primer contacto promedio
    vel = db.query(queries.SQL_VELOCITY, [p])
    if args.jornada:
        vel = [v for v in vel if v["IdPersonal"] in allowed]
    avg_min = (sum(v["Minutos"] for v in vel) / len(vel)) if vel else None
    if avg_min is None:
        avg_str = "—"
    elif avg_min < 60:
        avg_str = f"{round(avg_min)} min"
    elif avg_min < 1440:
        avg_str = f"{avg_min/60:.1f} h"
    else:
        avg_str = f"{avg_min/1440:.1f} días"

    tc_global = (total_m / total_l) if total_l else 0

    rows = [
        {"Metric": "Asesores activos", "Valor": activos, "Detalle": f"de {len(asesores)} en catálogo"},
        {"Metric": "Llamadas totales", "Valor": total_c + total_n, "Detalle": f"{total_c:,} cont · {total_n:,} no cont"},
        {"Metric": "Leads asignados", "Valor": total_l, "Detalle": ""},
        {"Metric": "Matriculaciones", "Valor": total_m, "Detalle": ""},
        {"Metric": "TC global", "Valor": fmt_pct(tc_global, 2), "Detalle": f"{total_m}/{total_l}" if total_l else ""},
        {"Metric": "Tiempo a primer contacto (prom)", "Valor": avg_str, "Detalle": f"n={len(vel):,}"},
    ]
    print(f"\n>>> Período: últimos {p} días" + (f" · jornada={args.jornada}" if args.jornada else "") + "\n", file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
