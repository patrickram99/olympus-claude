#!/usr/bin/env python3
"""
Comparación de TC de cohorte entre meses de captación, por programa.

Cohorte = leads de un programa CREADOS en un mes calendario (mes de captación).
Para comparar peras con peras entre meses usamos la **TC a N días de madurez**:
de los leads creados en el mes M, qué fracción llegó a IdEstado=3 dentro de los
N días siguientes a la creación de *cada* lead (default N=30). Así una cohorte de
abril y una de marzo se miden con la misma ventana de oportunidad de conversión.

Madurez de medición: a la fecha de corte sólo son "evaluables" los meses cuyos
leads ya tuvieron sus N días completos. Con corte a inicios de junio, mayo aún no
es plenamente evaluable a 30 días (sus leads recientes no han cumplido la ventana)
— el script marca esos meses como inmaduros y los excluye de la comparación de
crecimiento, mostrándolos aparte como lectura preliminar.

Programa (familia) = CodigoLanzamiento sin el sufijo MMYYN (imbpepcontfin05261 ->
imbpepcontfin), de modo que todas las relanzadas mensuales del mismo curso caen
en la misma familia.

Uso:
  python scripts/cohorte_tc_programas.py
  python scripts/cohorte_tc_programas.py --desde 2026-01-01 --mat-days 30 --min-leads 100
  python scripts/cohorte_tc_programas.py --mat-days 14            # lectura más temprana
  python scripts/cohorte_tc_programas.py --fmt csv -o cohortes.csv
"""
from __future__ import annotations

import argparse
import calendar
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cli, db
from lib.format import output

SUFFIX = re.compile(r"^(?P<fam>.+?)\d{2}\d{2}\d$")   # familia = código sin MMYYN
MESES = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
         7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}

SQL = """
SELECT pr.CodigoLanzamiento AS Codigo, pr.Nombre AS Nombre,
  YEAR(o.FechaCreacion) AS Y, MONTH(o.FechaCreacion) AS M,
  COUNT(DISTINCT o.Id) AS Leads,
  COUNT(DISTINCT CASE WHEN m3.f3 IS NOT NULL
        AND m3.f3 < DATEADD(day, ?, o.FechaCreacion) THEN o.Id END) AS ConvMat,
  COUNT(DISTINCT CASE WHEN m3.f3 IS NOT NULL THEN o.Id END) AS ConvAll
FROM adm.Producto pr
JOIN adm.Oportunidad o ON o.IdProducto = pr.Id AND o.Estado = 1
LEFT JOIN (
  SELECT IdOportunidad, MIN(FechaCreacion) AS f3
  FROM adm.HistorialEstado WHERE Estado = 1 AND IdEstado = 3 GROUP BY IdOportunidad
) m3 ON m3.IdOportunidad = o.Id
WHERE pr.Estado = 1 AND pr.CodigoLanzamiento IS NOT NULL AND o.FechaCreacion >= ?
GROUP BY pr.CodigoLanzamiento, pr.Nombre, YEAR(o.FechaCreacion), MONTH(o.FechaCreacion)
"""


def family_of(code: str) -> str:
    code = (code or "").strip()
    m = SUFFIX.match(code)
    return m.group("fam") if m else code


def main():
    ap = argparse.ArgumentParser(description="Comparación de TC de cohorte por mes de captación, por programa")
    ap.add_argument("--desde", type=cli.iso_date, default="2026-01-01", help="Sólo leads creados >= esta fecha (YYYY-MM-DD)")
    ap.add_argument("--mat-days", type=int, default=30, help="Ventana de madurez en días para la TC (default 30)")
    ap.add_argument("--min-leads", type=int, default=100, help="Mínimo de leads para incluir una cohorte familia×mes")
    ap.add_argument("--hoy", type=cli.iso_date, help="Fecha de corte (YYYY-MM-DD); default hoy del sistema")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    hoy = date.fromisoformat(args.hoy) if args.hoy else date.today()

    raw = db.query(SQL, [args.mat_days, args.desde])

    # familia -> (Y,M) -> agregados
    fams: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))  # [Leads, ConvMat, ConvAll]
    # fam -> ((Y,M), nombre): se queda el nombre de la cohorte más reciente,
    # determinista (antes dependía del orden en que la BD devolviera las filas).
    _fam_latest: dict[str, tuple] = {}
    for r in raw:
        fam = family_of(r["Codigo"])
        ym = (int(r["Y"]), int(r["M"]))
        agg = fams[fam][ym]
        agg[0] += int(r["Leads"] or 0)
        agg[1] += int(r["ConvMat"] or 0)
        agg[2] += int(r["ConvAll"] or 0)
        prev = _fam_latest.get(fam)
        cand = (ym, (r["Nombre"] or "").strip())
        if prev is None or cand > prev:   # desempata por nombre si el mes coincide
            _fam_latest[fam] = cand
    fam_name = {fam: nombre for fam, (_, nombre) in _fam_latest.items()}

    def evaluable(ym) -> bool:
        # el mes es evaluable a mat-days si TODO el mes ya cumplió la ventana
        y, m = ym
        last = date(y, m, calendar.monthrange(y, m)[1])
        return (hoy - last).days >= args.mat_days

    # ── Comparación cohorte-a-cohorte (familias con >=2 meses evaluables) ──────
    comp_rows = []
    for fam, months in fams.items():
        ev = {ym: a for ym, a in months.items() if evaluable(ym) and a[0] >= args.min_leads}
        if len(ev) < 2:
            continue
        orden = sorted(ev)
        def tc(a):  # ConvMat / Leads
            return round(a[1] / a[0] * 100, 2) if a[0] else 0.0
        prim, ult = ev[orden[0]], ev[orden[-1]]
        comp_rows.append({
            "Programa": fam_name.get(fam, fam)[:40],
            "Cohortes (TC a %dd)" % args.mat_days: " → ".join(
                f"{MESES[m]}:{tc(ev[(y, m)]):.2f}%" for (y, m) in orden),
            "Leads_ult": ult[0],
            "TC_prim": tc(prim),
            "TC_ult": tc(ult),
            "ΔTCpp": round(tc(ult) - tc(prim), 2),
        })
    comp_rows.sort(key=lambda x: (-x["ΔTCpp"], x["Programa"]))  # desempate estable

    # ── Tendencia agregada por mes de captación (todas las familias) ───────────
    by_month_ev = defaultdict(lambda: [0, 0])
    by_month_im = defaultdict(lambda: [0, 0])   # inmaduros: lectura preliminar
    for months in fams.values():
        for ym, a in months.items():
            tgt = by_month_ev if evaluable(ym) else by_month_im
            tgt[ym][0] += a[1]
            tgt[ym][1] += a[0]

    def trend_lines(d, tag):
        out = []
        for ym in sorted(d):
            conv, lds = d[ym]
            if lds < args.min_leads:
                continue
            tc = conv / lds * 100 if lds else 0
            out.append(f"     {MESES[ym[1]]} {ym[0]}:  TC{args.mat_days}d = {tc:5.2f}%   "
                       f"({conv:>4d}/{lds:>6d} leads){tag}")
        return out

    creci = [r for r in comp_rows if r["ΔTCpp"] > 0]
    cayo = [r for r in comp_rows if r["ΔTCpp"] < 0]

    hdr = [
        "",
        f">>> TC de cohorte por mes de CAPTACIÓN del lead  ·  madurez {args.mat_days} días  ·  corte {hoy.isoformat()}",
        f">>> Familias con >=2 meses evaluables (>= {args.min_leads} leads): {len(comp_rows)}  "
        f"·  crecieron: {len(creci)}  ·  cayeron: {len(cayo)}",
        "",
        f">>> TENDENCIA AGREGADA — TC a {args.mat_days} días por mes de captación:",
        *trend_lines(by_month_ev, ""),
        *trend_lines(by_month_im, "  [INMADURO: aún no cumple la ventana, lectura parcial]"),
        "",
        f">>> TC = convertidos dentro de {args.mat_days}d de la creación del lead / leads del mes (apples-to-apples).",
        ">>> Meses inmaduros excluidos de la comparación de crecimiento.",
        "",
    ]
    print("\n".join(hdr), file=sys.stderr)

    cols = ["Programa", "Cohortes (TC a %dd)" % args.mat_days, "Leads_ult", "TC_prim", "TC_ult", "ΔTCpp"]
    output(comp_rows, fmt=args.fmt, out_path=args.output, headers=cols)


if __name__ == "__main__":
    main()
