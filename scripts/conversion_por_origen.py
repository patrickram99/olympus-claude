#!/usr/bin/env python3
"""
Compara la tasa de conversión global de cada ORIGEN del lead.

Origen = canal de captación en Oportunidad.Origen (Linkedin, Manual, Wordpress,
FormularioWeb, NULL). Convertido = la oportunidad alcanzó alguna vez estado
Matriculado (IdEstado=3). Ordena por volumen e incluye Wilson LB 95% porque los
tamaños de muestra son muy dispares (decenas vs cientos de miles).

Uso:
  python scripts/conversion_por_origen.py
  python scripts/conversion_por_origen.py --desde 2026-01-01 --hasta 2026-06-01
  python scripts/conversion_por_origen.py --incluir-eliminados
  python scripts/conversion_por_origen.py --fmt csv -o origenes.csv

Caveat de interpretación: las TC NO son comparables a igualdad de intención.
"Manual" sufre sesgo de selección (el asesor crea el lead cuando ya está caliente);
"FormularioWeb"/"Wordpress" son inbound de alta intención; "Linkedin" es lead-gen
frío y masivo. Para decidir presupuesto, cruzar con costo (CPL × leads) → costo
por matrícula, no quedarse en la TC sola.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.calc import wilson_lb
from lib.format import output

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _valid_date(s: str | None) -> str | None:
    if s and not _ISO.fullmatch(s):
        print(f"ERROR: fecha debe ser YYYY-MM-DD, recibido: {s!r}", file=sys.stderr)
        sys.exit(2)
    return s


def main():
    ap = argparse.ArgumentParser(description="TC global por origen del lead (con Wilson LB)")
    ap.add_argument("--desde", help="Filtra Oportunidad.FechaCreacion >= YYYY-MM-DD")
    ap.add_argument("--hasta", help="Filtra Oportunidad.FechaCreacion <= YYYY-MM-DD (inclusive)")
    ap.add_argument("--incluir-eliminados", action="store_true",
                    help="Incluye oportunidades soft-deleted (Estado=0). Por defecto sólo activas.")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    desde = _valid_date(args.desde)
    hasta = _valid_date(args.hasta)

    sql, params = queries.sql_conversion_por_origen(
        incluir_eliminados=args.incluir_eliminados, desde=desde, hasta=hasta
    )
    data = db.query(sql, params)

    total_mat = sum(int(r["Matriculas"]) for r in data) or 1

    rows = []
    for r in data:
        leads = int(r["Leads"])
        mat = int(r["Matriculas"])
        tc = (mat / leads) if leads else 0.0
        rows.append({
            "Origen": r["Origen"],
            "Leads": leads,
            "Matriculas": mat,
            "TC%": round(tc * 100, 3),
            "WilsonLB%": round(wilson_lb(mat, leads) * 100, 3),
            "%MatricTotal": round(100.0 * mat / total_mat, 1),
        })

    rows.sort(key=lambda x: -x["Leads"])

    # Fila TOTAL
    tot_leads = sum(x["Leads"] for x in rows)
    tot_mat = sum(x["Matriculas"] for x in rows)
    rows.append({
        "Origen": "TOTAL",
        "Leads": tot_leads,
        "Matriculas": tot_mat,
        "TC%": round(100.0 * tot_mat / tot_leads, 3) if tot_leads else 0,
        "WilsonLB%": "",
        "%MatricTotal": 100.0,
    })

    ventana = f"{desde or 'inicio'} → {hasta or 'hoy'}"
    estado = "todas (incl. eliminadas)" if args.incluir_eliminados else "sólo activas"
    print(f"\n>>> Conversión por origen · {ventana} · {estado}\n", file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
