#!/usr/bin/env python3
"""
Performance de programas en una ventana: combina conversión, esfuerzo de asesor
(llamadas) y dinero generado. NO usa cohortes — TC es de ventana (flujo).

Por producto, en la ventana [desde, hasta) (default últimos --periodo días):
  - Leads        : oportunidades creadas en la ventana.
  - Ventas       : matrículas (IdEstado=3) cerradas en la ventana.
  - TC%          : Ventas / Leads (conversión de ventana, NO cohorte).
  - Llamadas     : llamadas hechas a oportunidades del programa en la ventana
                   (delta de los contadores acumulativos, negativos clampados a 0),
                   contestadas + no contestadas. Proxy de TIEMPO DE ASESOR.
  - Llam/Venta   : llamadas por matrícula — esfuerzo por venta (menos = mejor).
  - CobrPEN      : dinero efectivamente cobrado de las ventas de la ventana (PEN).
  - ComprPEN     : dinero comprometido de esas ventas (PEN).
  - Cobr/Llam    : PEN cobrado por llamada — dinero por unidad de esfuerzo (más = mejor).
  - Ticket       : CobrPEN / Venta.

PerfScore (0-100): promedio simple de tres dimensiones normalizadas min-max sobre
los programas con Ventas >= --min-ventas: TC%, CobrPEN (dinero) y eficiencia de
esfuerzo (-Llam/Venta). Es un resumen transparente; las columnas crudas quedan a
la vista para que puedas re-ponderar.

Uso:
  python scripts/programas_performance.py --periodo 60
  python scripts/programas_performance.py --periodo 60 --min-ventas 5 --top 20
  python scripts/programas_performance.py --desde 2026-04-03 --hasta 2026-06-03
  python scripts/programas_performance.py --periodo 60 --orden cobrado|score|eficiencia
  python scripts/programas_performance.py --periodo 60 --fmt csv -o perf.csv
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.calc import CostParams
from lib.format import output

ISO = re.compile(r"\d{4}-\d{2}-\d{2}")

# Llamadas (delta de contadores acumulativos) atribuidas al producto del lead.
SQL_LLAMADAS_POR_PRODUCTO = """
SELECT o.IdProducto AS P,
  SUM(q.dCc) AS Contestadas,
  SUM(q.dCn) AS NoContestadas
FROM (
  SELECT he.IdOportunidad,
    CASE WHEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCc,
    CASE WHEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.FechaCreacion >= ? AND he.FechaCreacion < ?
) q
INNER JOIN adm.Oportunidad o ON o.Id = q.IdOportunidad AND o.Estado = 1
GROUP BY o.IdProducto
"""


def _norm(vals: dict, key, invert=False):
    xs = [v[key] for v in vals]
    lo, hi = min(xs), max(xs)
    span = (hi - lo) or 1.0
    for v in vals:
        z = (v[key] - lo) / span
        v["_n_" + key] = (1 - z) if invert else z


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Performance de programas: TC + llamadas (esfuerzo) + dinero")
    ap.add_argument("--periodo", type=int, default=60, help="Ventana en días hacia atrás desde hoy (default 60)")
    ap.add_argument("--desde", help="Override fecha inicio inclusiva (YYYY-MM-DD)")
    ap.add_argument("--hasta", help="Override fecha fin EXCLUSIVA (YYYY-MM-DD)")
    ap.add_argument("--hoy", help="Fecha de corte (YYYY-MM-DD); default hoy del sistema")
    ap.add_argument("--min-ventas", type=int, default=5, help="Mínimo de ventas para el ranking/score (default 5)")
    ap.add_argument("--min-leads", type=int, default=200,
                    help="Mínimo de leads en ventana para el score; corta denominadores minúsculos "
                         "(productos duplicados/pre-vendidos) que inflan TC y eficiencia (default 200)")
    ap.add_argument("--top", type=int, default=20, help="Cuántos programas mostrar")
    ap.add_argument("--ids", help="Lista de IdProducto separados por coma para restringir a esos programas "
                                  "(p. ej. comparar su historia completa con --desde 2026-01-01)")
    ap.add_argument("--orden", choices=["cobrado", "score", "eficiencia", "tc", "ventas"], default="score",
                    help="Criterio de orden de la tabla (default score)")
    ap.add_argument("--usd-pen", type=float, help="Override USD->PEN (default .env / 3.78)")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    hoy = date.fromisoformat(args.hoy) if args.hoy else date.today()
    if args.desde and args.hasta:
        desde, hasta = args.desde, args.hasta
    else:
        desde = (hoy - timedelta(days=args.periodo)).isoformat()
        hasta = (hoy + timedelta(days=1)).isoformat()   # incluir todo hoy
    for label, val in (("--desde", desde), ("--hasta", hasta)):
        if not ISO.fullmatch(val):
            print(f"ERROR: {label} debe ser YYYY-MM-DD, recibido: {val!r}", file=sys.stderr)
            sys.exit(2)

    usd_pen = args.usd_pen if args.usd_pen is not None else CostParams.from_env().usd_pen

    ids = None
    if args.ids:
        try:
            ids = {int(x) for x in args.ids.split(",") if x.strip()}
        except ValueError:
            print(f"ERROR: --ids debe ser una lista de enteros separados por coma, recibido: {args.ids!r}", file=sys.stderr)
            sys.exit(2)

    ventas_rows = db.query(queries.SQL_PROGRAMAS_TOP_VENTAS, [desde, hasta] * 5)
    if ids is not None:
        ventas_rows = [r for r in ventas_rows if int(r["Id"]) in ids]
    llam_rows = db.query(SQL_LLAMADAS_POR_PRODUCTO, [desde, hasta])
    llam = {int(r["P"]): (int(r["Contestadas"] or 0), int(r["NoContestadas"] or 0)) for r in llam_rows}

    rows = []
    for r in ventas_rows:
        pid = int(r["Id"])
        leads = int(r["Leads"] or 0)
        ventas = int(r["Ventas"] or 0)
        cont, nocont = llam.get(pid, (0, 0))
        llamadas = cont + nocont
        cobr = float(r["CobradoUSD"] or 0) * usd_pen
        compr = float(r["ComprometidoUSD"] or 0) * usd_pen
        rows.append({
            "Id": pid,
            "Codigo": (r["Codigo"] or "").strip() or "—",
            "Programa": (r["Nombre"] or "").strip()[:38],
            "Leads": leads,
            "Ventas": ventas,
            "TC%": round(ventas / leads * 100, 2) if leads else None,
            "Llamadas": llamadas,
            "Cont%": round(cont / llamadas * 100, 1) if llamadas else None,
            "Llam/Vta": round(llamadas / ventas, 1) if ventas else None,
            "CobrPEN": round(cobr, 0),
            "ComprPEN": round(compr, 0),
            "%Cobr": round(cobr / compr * 100, 1) if compr else None,
            "Cobr/Llam": round(cobr / llamadas, 1) if llamadas else None,
            "Ticket": round(cobr / ventas, 0) if ventas else None,
        })

    # ── Score sobre programas con ventas suficientes ──────────────────────────
    elig = [r for r in rows if r["Ventas"] >= args.min_ventas and r["Leads"] >= args.min_leads
            and r["Llamadas"] > 0 and r["TC%"] is not None]
    for r in elig:
        r["_eff"] = r["Llam/Vta"]            # menor = mejor
        r["_tc"] = r["TC%"]
        r["_cobr"] = r["CobrPEN"]
    if elig:
        _norm(elig, "_tc")
        _norm(elig, "_cobr")
        _norm(elig, "_eff", invert=True)     # menos llamadas/venta => mejor
        for r in elig:
            r["PerfScore"] = round((r["_n__tc"] + r["_n__cobr"] + r["_n__eff"]) / 3 * 100, 1)
    for r in rows:
        r.setdefault("PerfScore", None)
        for k in list(r):
            if k.startswith("_"):
                del r[k]

    key = {
        "cobrado": lambda x: -(x["CobrPEN"] or 0),
        "ventas": lambda x: -(x["Ventas"] or 0),
        "tc": lambda x: -(x["TC%"] or 0),
        "eficiencia": lambda x: (x["Llam/Vta"] if x["Llam/Vta"] is not None else 9e9),
        "score": lambda x: -(x["PerfScore"] if x["PerfScore"] is not None else -1),
    }[args.orden]
    rows.sort(key=key)
    top = rows[:args.top]

    # ── Callouts ──────────────────────────────────────────────────────────────
    tot_cobr = sum(r["CobrPEN"] for r in rows)
    tot_llam = sum(r["Llamadas"] for r in rows)
    tot_vtas = sum(r["Ventas"] for r in rows)
    best_eff = sorted([r for r in elig], key=lambda x: x["Llam/Vta"])[:3]
    worst_eff = sorted([r for r in elig], key=lambda x: -x["Llam/Vta"])[:3]
    best_money_eff = sorted([r for r in elig], key=lambda x: -(x["Cobr/Llam"] or 0))[:3]

    def _l(r, field, suf=""):
        return f"     {r['Codigo']:<26} {r['Programa'][:30]:<30} {r[field]}{suf}  (V={r['Ventas']})"

    hdr = [
        "",
        f">>> PERFORMANCE DE PROGRAMAS · ventana [{desde} -> {hasta})  ·  USD/PEN={usd_pen}",
        f">>> Programas con venta: {len(rows)}  ·  elegibles para score (V>={args.min_ventas}): {len(elig)}  ·  orden: {args.orden}",
        f">>> Totales ventana: {tot_vtas:,} ventas · {tot_llam:,} llamadas · {tot_cobr:,.0f} PEN cobrados "
        f"· {tot_llam/tot_vtas:,.1f} llam/venta global" if tot_vtas else "",
        "",
        ">>> MÁS EFICIENTES (menos llamadas por venta):",
        *[_l(r, "Llam/Vta", " llam/vta") for r in best_eff],
        ">>> MENOS EFICIENTES (más llamadas por venta — queman tiempo de asesor):",
        *[_l(r, "Llam/Vta", " llam/vta") for r in worst_eff],
        ">>> MÁS DINERO POR LLAMADA (mejor retorno al esfuerzo):",
        *[_l(r, "Cobr/Llam", " PEN/llam") for r in best_money_eff],
        "",
        ">>> TC=ventana(no cohorte) · Llamadas=delta acumulado (1ra fila in-window cuenta su acumulado, leve sobreconteo).",
        "",
    ]
    print("\n".join(h for h in hdr if h is not None), file=sys.stderr)

    cols = ["Id", "Codigo", "Programa", "Leads", "Ventas", "TC%", "Llamadas", "Cont%",
            "Llam/Vta", "CobrPEN", "%Cobr", "Cobr/Llam", "Ticket", "PerfScore"]
    output(top, fmt=args.fmt, out_path=args.output, headers=cols)


if __name__ == "__main__":
    main()
