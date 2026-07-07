#!/usr/bin/env python3
"""
Top de programas (productos) por ventas en una ventana de fechas, comparando
ventas vs. leads con TC de cohorte e ingresos (comprometido y cobrado).

Por producto, en la ventana [--desde, --hasta) (hasta exclusivo):
  - Ventas      : matrículas cerradas en la ventana (flujo) — criterio de ranking.
  - Leads       : oportunidades CREADAS en la ventana (cohorte de captación).
  - Conv        : de esos leads, cuántos ya convirtieron (numerador de TC cohorte).
  - TC%         : Conv / Leads — conversión de cohorte, apples-to-apples.
  - ComprPEN    : cobranza comprometida (CobranzaPlan.Total) de las ventas, en PEN.
  - CobrPEN     : cobranza efectivamente cobrada (CobranzaPago.Monto), en PEN.
  - %Cobr       : CobrPEN / ComprPEN — qué fracción del compromiso ya entró en caja.

Incluye un análisis agregado de % cobrado y un guard contra ComprPEN corruptos
(tickets implausibles por venta), que se marcan y se excluyen del agregado.

Uso:
  python scripts/programas_top_ventas.py
  python scripts/programas_top_ventas.py --desde 2026-04-01 --hasta 2026-06-01 --top 25
  python scripts/programas_top_ventas.py --top 40 --usd-pen 3.85
  python scripts/programas_top_ventas.py --fmt csv -o top_ventas.csv
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cli, db, queries
from lib.calc import CostParams
from lib.format import output

ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def main():
    ap = argparse.ArgumentParser(description="Top de programas por ventas con TC cohorte e ingresos")
    ap.add_argument("--desde", default="2026-04-01", help="Fecha inicio inclusiva (YYYY-MM-DD)")
    ap.add_argument("--hasta", default="2026-06-01", help="Fecha fin EXCLUSIVA (YYYY-MM-DD)")
    ap.add_argument("--top", type=cli.top_type, default=25, help="Número de programas a mostrar")
    ap.add_argument("--usd-pen", type=float, help="Override tipo de cambio USD->PEN (default .env / 3.78)")
    ap.add_argument("--max-usd-por-venta", type=float, default=5000.0,
                    help="Ticket comprometido/venta sobre el cual se marca el dato como sospechoso "
                         "y se excluye del agregado de %% cobrado")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    for label, val in (("--desde", args.desde), ("--hasta", args.hasta)):
        if not ISO.fullmatch(val):
            print(f"ERROR: {label} debe ser YYYY-MM-DD, recibido: {val!r}", file=sys.stderr)
            sys.exit(2)

    usd_pen = args.usd_pen if args.usd_pen is not None else CostParams.from_env().usd_pen

    raw = db.query(queries.SQL_PROGRAMAS_TOP_VENTAS, [args.desde, args.hasta])

    rows = []
    for r in raw:
        leads = int(r["Leads"] or 0)
        ventas = int(r["Ventas"] or 0)
        conv = int(r["ConvCohorte"] or 0)
        compr_pen = float(r["ComprometidoUSD"] or 0) * usd_pen
        cobr_pen = float(r["CobradoUSD"] or 0) * usd_pen

        ticket = (compr_pen / ventas) if ventas else 0.0
        sospechoso = ticket > args.max_usd_por_venta * usd_pen

        rows.append({
            "Id": int(r["Id"]),
            "Codigo": (r["Codigo"] or "").strip() or "—",
            "Programa": (r["Nombre"] or "").strip()[:42] + (" (!)" if sospechoso else ""),
            "Leads": leads,
            "Ventas": ventas,
            "Conv": conv,
            "TC%": round(conv / leads * 100, 2) if leads else None,
            "ComprPEN": round(compr_pen, 2),
            "CobrPEN": round(cobr_pen, 2),
            "%Cobr": round(cobr_pen / compr_pen * 100, 1) if compr_pen else None,
            "_sosp": sospechoso,
        })

    # Ranking por ventas (flujo), desempate por caja cobrada.
    rows.sort(key=lambda x: (-x["Ventas"], -x["CobrPEN"]))
    top = rows[:args.top]

    # ── Análisis de % cobrado (sobre el top, excluyendo sospechosos) ──────────
    limpios = [r for r in top if not r["_sosp"]]
    tot_comp = sum(r["ComprPEN"] for r in limpios)
    tot_cobr = sum(r["CobrPEN"] for r in limpios)
    pct_global = (tot_cobr / tot_comp * 100) if tot_comp else 0.0

    con_muestra = [r for r in limpios if r["Ventas"] >= 5 and r["%Cobr"] is not None]
    prom_simple = (sum(r["%Cobr"] for r in con_muestra) / len(con_muestra)) if con_muestra else 0.0
    mejores = sorted(con_muestra, key=lambda x: -x["%Cobr"])[:3]
    peores = sorted(con_muestra, key=lambda x: x["%Cobr"])[:3]
    sospechosos = [r for r in top if r["_sosp"]]

    def _line(r):
        return f"     {r['Codigo']:<18} {r['Programa'][:34]:<34} {r['%Cobr']:>5.1f}%  (V={r['Ventas']})"

    hdr = [
        "",
        f">>> Ventana: [{args.desde} -> {args.hasta})  ·  TC/PEN @ USD/PEN={usd_pen}",
        f">>> Programas con ventas: {len(rows)}  ·  mostrando top {len(top)} por ventas",
        "",
        ">>> ANÁLISIS DE % COBRADO (top mostrado, excl. sospechosos):",
        f"     Comprometido: {tot_comp:>14,.0f} PEN",
        f"     Cobrado:      {tot_cobr:>14,.0f} PEN",
        f"     % cobrado global (ponderado): {pct_global:5.1f}%",
        f"     % cobrado promedio (simple, V>=5): {prom_simple:5.1f}%",
        "",
        "     Mejor cobranza:",
        *[_line(r) for r in mejores],
        "     Cobranza más rezagada:",
        *[_line(r) for r in peores],
    ]
    if sospechosos:
        hdr += [
            "",
            f">>> [!] {len(sospechosos)} programa(s) con ComprPEN sospechoso (ticket/venta > "
            f"{args.max_usd_por_venta:,.0f} USD) -- excluidos del agregado, revisar en la fuente:",
            *[f"     {r['Codigo']} · {r['Programa'][:40]} · Compr={r['ComprPEN']:,.0f} PEN / {r['Ventas']} ventas"
              for r in sospechosos],
        ]
    print("\n".join(hdr) + "\n", file=sys.stderr)

    cols = ["Id", "Codigo", "Programa", "Leads", "Ventas", "Conv", "TC%", "ComprPEN", "CobrPEN", "%Cobr"]
    output(top, fmt=args.fmt, out_path=args.output, headers=cols)


if __name__ == "__main__":
    main()
