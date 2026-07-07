#!/usr/bin/env python3
"""
Compara asesores por ÁREA temática del programa (Finanzas / RRHH / Otras),
para testear si un área "consolidada" tiene asesores que rinden distinto.

Dos vistas:
  1) NIVEL ÁREA (pooled): junta todo lo trabajado en cada área (por cualquier
     asesor) -> TC, llamadas/lead, llamadas/venta. Mide si el área es "fácil"
     (TC alta con poco esfuerzo) o "dura".
  2) NIVEL ASESOR (home area): clasifica a cada asesor en el área donde tiene
     MÁS leads, y promedia su output (matrículas), TC y esfuerzo. Mide si los
     asesores de un área producen mediocre o no.

Área se infiere del nombre del producto (configurable abajo en AREAS).
Llamadas = delta de contadores acumulativos (negativos clampados).
Ventana: leads/actividad con FechaCreacion >= --desde (default 2026-01-01).

Uso:
  python scripts/asesores_por_area.py
  python scripts/asesores_por_area.py --desde 2026-03-01 --min-leads 50
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cli, db, queries
from lib.calc import wilson_lb
from lib.format import output

# Clasificación de área por patrón en el nombre del producto (LIKE, case-insensitive).
AREA_CASE = """
  CASE WHEN pr.Nombre LIKE '%financ%' OR pr.Nombre LIKE '%finanz%' OR pr.Nombre LIKE '%controller%'
            OR pr.Nombre LIKE '%fp&a%' OR pr.Nombre LIKE '%pricing%' THEN 'Finanzas'
       WHEN pr.Nombre LIKE '%recursos humanos%' THEN 'RRHH'
       ELSE 'Otras' END
"""

SQL_LEADS_MATRIC = f"""
SELECT he.IdPersonal, {AREA_CASE} AS Area,
  COUNT(DISTINCT he.IdOportunidad) AS Leads,
  COUNT(DISTINCT CASE WHEN he.IdEstado=3 THEN he.IdOportunidad END) AS Matric
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad o ON o.Id=he.IdOportunidad AND o.Estado=1
INNER JOIN adm.Producto pr ON pr.Id=o.IdProducto AND pr.Estado=1
WHERE he.Estado=1 AND he.IdPersonal IS NOT NULL AND he.FechaCreacion >= ?
GROUP BY he.IdPersonal, {AREA_CASE}
"""

SQL_LLAMADAS = f"""
SELECT q.IdPersonal, {AREA_CASE} AS Area, SUM(q.dCc + q.dCn) AS Llamadas
FROM ({queries.sql_llamadas_delta(
    "he.IdPersonal, he.IdOportunidad",
    "he.IdPersonal IS NOT NULL AND he.FechaCreacion >= ?",
)}) q
INNER JOIN adm.Oportunidad o ON o.Id=q.IdOportunidad AND o.Estado=1
INNER JOIN adm.Producto pr ON pr.Id=o.IdProducto AND pr.Estado=1
GROUP BY q.IdPersonal, {AREA_CASE}
"""

AREAS = ["Finanzas", "RRHH", "Otras"]


def main():
    ap = argparse.ArgumentParser(description="Comparación de asesores por área (Finanzas/RRHH/Otras)")
    ap.add_argument("--desde", type=cli.iso_date, default="2026-01-01", help="Actividad con FechaCreacion >= (YYYY-MM-DD)")
    ap.add_argument("--min-leads", type=int, default=80,
                    help="Mínimo de leads en su área hogar para incluir al asesor en la vista por asesor")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    lm = db.query(SQL_LEADS_MATRIC, [args.desde])
    ll = db.query(SQL_LLAMADAS, [args.desde])

    # (asesor, area) -> dict
    cell = defaultdict(lambda: {"Leads": 0, "Matric": 0, "Llamadas": 0})
    for r in lm:
        c = cell[(int(r["IdPersonal"]), r["Area"])]
        c["Leads"] += int(r["Leads"] or 0)
        c["Matric"] += int(r["Matric"] or 0)
    for r in ll:
        cell[(int(r["IdPersonal"]), r["Area"])]["Llamadas"] += int(r["Llamadas"] or 0)

    # ── Vista 1: nivel ÁREA (pooled) ──────────────────────────────────────────
    area_tot = {a: {"Leads": 0, "Matric": 0, "Llamadas": 0, "Asesores": set()} for a in AREAS}
    for (aid, area), c in cell.items():
        t = area_tot[area]
        t["Leads"] += c["Leads"]; t["Matric"] += c["Matric"]; t["Llamadas"] += c["Llamadas"]
        if c["Leads"] > 0:
            t["Asesores"].add(aid)
    area_rows = []
    for a in AREAS:
        t = area_tot[a]
        area_rows.append({
            "Area": a,
            "Asesores": len(t["Asesores"]),
            "Leads": t["Leads"],
            "Matric": t["Matric"],
            "TC%": round(t["Matric"] / t["Leads"] * 100, 2) if t["Leads"] else None,
            "Llamadas": t["Llamadas"],
            "Llam/Lead": round(t["Llamadas"] / t["Leads"], 2) if t["Leads"] else None,
            "Llam/Venta": round(t["Llamadas"] / t["Matric"], 0) if t["Matric"] else None,
        })

    # ── Vista 2: nivel ASESOR (home area = área con más leads) ─────────────────
    by_asesor = defaultdict(lambda: defaultdict(lambda: {"Leads": 0, "Matric": 0, "Llamadas": 0}))
    for (aid, area), c in cell.items():
        d = by_asesor[aid][area]
        d["Leads"] += c["Leads"]; d["Matric"] += c["Matric"]; d["Llamadas"] += c["Llamadas"]

    home_group = {a: [] for a in AREAS}   # area -> lista de dicts por asesor (en su área hogar)
    for aid, areas in by_asesor.items():
        home = max(areas, key=lambda a: areas[a]["Leads"])
        h = areas[home]
        if h["Leads"] < args.min_leads:
            continue
        home_group[home].append({
            "Leads": h["Leads"], "Matric": h["Matric"], "Llamadas": h["Llamadas"],
            "TotalMatric": sum(v["Matric"] for v in areas.values()),
        })

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    def med(xs):
        s = sorted(xs)
        n = len(s)
        if n == 0:
            return 0.0
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    asesor_rows = []
    for a in AREAS:
        g = home_group[a]
        if not g:
            asesor_rows.append({"Area": a, "Asesores": 0})
            continue
        leads = [x["Leads"] for x in g]
        matr = [x["Matric"] for x in g]
        llam = [x["Llamadas"] for x in g]
        tcs = [x["Matric"] / x["Leads"] * 100 for x in g if x["Leads"]]
        lpl = [x["Llamadas"] / x["Leads"] for x in g if x["Leads"]]
        tot_l, tot_m = sum(leads), sum(matr)
        asesor_rows.append({
            "Area": a,
            "Asesores": len(g),
            "Leads/ases (prom)": round(avg(leads), 0),
            "Matríc/ases (prom)": round(avg(matr), 1),
            "Matríc/ases (mediana)": round(med(matr), 1),
            "TC% (pooled)": round(tot_m / tot_l * 100, 2) if tot_l else None,
            "TC% (prom ases)": round(avg(tcs), 2),
            "Llam/Lead (prom ases)": round(avg(lpl), 1),
            "WilsonLB% (pooled)": round(wilson_lb(tot_m, tot_l) * 100, 2),
        })

    hdr = [
        "",
        f">>> ASESORES POR ÁREA  ·  actividad desde {args.desde}  ·  área hogar = donde el asesor tiene más leads",
        f">>> Vista asesor: incluye asesores con >= {args.min_leads} leads en su área hogar",
        "",
        ">>> VISTA 1 — NIVEL ÁREA (pooled): ¿es el área 'fácil' (TC alta, poco esfuerzo) o 'dura'?",
    ]
    print("\n".join(hdr), file=sys.stderr)
    output(area_rows, fmt="table",
           headers=["Area", "Asesores", "Leads", "Matric", "TC%", "Llamadas", "Llam/Lead", "Llam/Venta"])

    print("\n>>> VISTA 2 — NIVEL ASESOR (clasificado por área hogar): ¿producen mediocre?\n", file=sys.stderr)
    output(asesor_rows, fmt=args.fmt, out_path=args.output,
           headers=["Area", "Asesores", "Leads/ases (prom)", "Matríc/ases (prom)", "Matríc/ases (mediana)",
                    "TC% (pooled)", "TC% (prom ases)", "Llam/Lead (prom ases)", "WilsonLB% (pooled)"])


if __name__ == "__main__":
    main()
