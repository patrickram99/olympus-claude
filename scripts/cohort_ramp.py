#!/usr/bin/env python3
"""
Ramp-up de asesores nuevos por cohorte.

Para cada asesor con FechaIngreso efectiva `>= --since`, muestra una fila con
sus leads y matrículas en cada uno de los primeros N meses desde su ingreso.

Sales mode (default):
  FechaIngreso efectiva = MAX(FechaIngreso, SALES_DATA_START) — porque los
  datos de ventas sólo se registran desde 2026-01-01. Los 111 asesores con
  ingreso pre-CRM aparecen en el cohort de enero 2026 con su M1 contando
  desde esa fecha.

HR mode (--hr-mode):
  Usa la `FechaIngreso` real, para análisis de tenure/rotación. Útil para
  "qué tan rápido se va el talento que entra".

"Mes 1" cubre los días 1-30 después de la FechaIngreso efectiva
(DATEDIFF(month, …) = 0 → +1).

Atribución de leads: mismo patrón que `SQL_LEADS_ASIGNADOS` (rn=1).
Matrículas: dedup con `COUNT(DISTINCT IdOportunidad)` para evitar el bug
de las ~120 oportunidades con múltiples filas IdEstado=3.

Uso:
  python scripts/cohort_ramp.py --since 2026-01-01
  python scripts/cohort_ramp.py --since 2026-03-01 --meses 4
  python scripts/cohort_ramp.py --hr-mode --since 2025-01-01
  python scripts/cohort_ramp.py --since 2026-01-01 -o ramp.csv --fmt csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="Ramp-up por asesor en los primeros N meses")
    ap.add_argument("--since", default="2020-01-01", help="Filtrar FechaIngreso efectiva >= esta fecha (YYYY-MM-DD)")
    ap.add_argument("--meses", type=int, default=6, help="Cantidad de meses a mostrar (default 6)")
    ap.add_argument("--hr-mode", action="store_true", help="Usar FechaIngreso real (para análisis HR/rotación).")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    n_meses = max(1, args.meses)

    sql_ases = queries.sql_asesores_ingreso_desde(hr_mode=args.hr_mode)
    sql_leads = queries.sql_cohort_leads(hr_mode=args.hr_mode)
    sql_matric = queries.sql_cohort_matriculas(hr_mode=args.hr_mode)

    asesores = db.query(sql_ases, [args.since])
    leads_rows = db.query(sql_leads, [args.since])
    matric_rows = db.query(sql_matric, [args.since])

    # (IdPersonal, MesOffset) → count
    leads_by = {(int(r["IdPersonal"]), int(r["MesOffset"])): int(r["LeadsAsignados"]) for r in leads_rows}
    matric_by = {(int(r["IdPersonal"]), int(r["MesOffset"])): int(r["Matriculas"]) for r in matric_rows}

    rows = []
    for a in asesores:
        aid = int(a["Id"])
        rec = {
            "Id": aid,
            "Asesor": a["Nombre"],
            "Jornada": "TC" if a["Jornada"] == 31 else "TP",
            "IngresoReal": a["FechaIngresoReal"],
            "IngresoEfectivo": a["FechaIngresoEfectiva"],
        }
        total_leads = 0
        total_matric = 0
        for m in range(1, n_meses + 1):
            ml = leads_by.get((aid, m), 0)
            mm = matric_by.get((aid, m), 0)
            rec[f"M{m}_Leads"] = ml
            rec[f"M{m}_Matric"] = mm
            total_leads += ml
            total_matric += mm
        rec["Total_Leads"] = total_leads
        rec["Total_Matric"] = total_matric
        rows.append(rec)

    # Sort by total matric desc, then total leads desc, so the top performers
    # of the cohort surface first.
    rows.sort(key=lambda r: (-r["Total_Matric"], -r["Total_Leads"]))

    modo = "HR (FechaIngreso real)" if args.hr_mode else f"sales (cap={queries.SALES_DATA_START})"
    print(
        f"\n>>> Modo: {modo} · Cohorte >= {args.since} · {len(asesores)} asesores · ventana {n_meses} meses\n",
        file=sys.stderr,
    )
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
