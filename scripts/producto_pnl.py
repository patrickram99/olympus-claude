#!/usr/bin/env python3
"""
P&L y análisis de sensibilidad para un producto.

Uso:
  python scripts/producto_pnl.py 381                                # P&L con defaults
  python scripts/producto_pnl.py 381 --ingreso comprometido         # asumiendo 100% cobranza
  python scripts/producto_pnl.py 381 --salario 600 --cpl 0.25       # override de parámetros
  python scripts/producto_pnl.py 381 --fmt json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.calc import CostParams, ProductBaseline, compute_pnl, fte_equivalents
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="P&L de un producto con análisis de sensibilidad")
    ap.add_argument("producto_id", type=int, help="ID del producto (de adm.Producto)")
    ap.add_argument("--ingreso", choices=["cobrado", "comprometido"], default="cobrado")
    ap.add_argument("--salario", type=float, help="Override salario base PEN")
    ap.add_argument("--cpl", type=float, help="Override CPL USD")
    ap.add_argument("--comision-asesor", type=float, help="Override comisión asesor (0.10 = 10%%)")
    ap.add_argument("--comision-admin", type=float, help="Override comisión admin")
    ap.add_argument("--docente", type=float, help="Override costo docente USD")
    ap.add_argument("--usd-pen", type=float, help="Override tipo de cambio USD->PEN")
    ap.add_argument("--moneda", choices=["usd", "pen"], default="usd",
                    help="Moneda de las columnas de plata del P&L. 'usd' (DEFAULT): convierte "
                         "los montos PEN a USD dividiendo por USD/PEN. 'pen': montos en soles. "
                         "Los ratios (Margen %%, Break-even TC) y el CPL máx (ya en USD) no cambian.")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    pid = args.producto_id

    # KPIs base del producto
    kpis = db.query_one(queries.SQL_PRODUCT_KPIS, [pid, pid, pid, pid, pid, pid, pid])
    if not kpis or not kpis.get("TotalLeads"):
        print(f"Producto {pid} no encontrado o sin leads.", file=sys.stderr)
        sys.exit(1)

    # FTE attribution
    leads_prod = {r["IdPersonal"]: r["LeadsProducto"] for r in db.query(queries.SQL_LEADS_PRODUCTO_POR_ASESOR, [pid])}
    leads_tot = {r["IdPersonal"]: r["LeadsTotal"] for r in db.query(queries.SQL_LEADS_TOTAL_POR_ASESOR)}
    fte = fte_equivalents(leads_prod, leads_tot)

    baseline = ProductBaseline(
        leads=int(kpis["TotalLeads"]),
        matriculados=int(kpis["Matriculados"] or 0),
        fte=fte,
        monto_comprometido_usd=float(kpis["MontoComprometidoUSD"] or 0),
        monto_cobrado_usd=float(kpis["MontoCobradoUSD"] or 0),
        costo_base_usd=float(kpis["CostoBaseUSD"] or 0),
    )

    params = CostParams.from_env()
    if args.salario is not None: params.salario_base_pen = args.salario
    if args.cpl is not None: params.cpl_usd = args.cpl
    if args.comision_asesor is not None: params.comision_asesor_pct = args.comision_asesor
    if args.comision_admin is not None: params.comision_admin_pct = args.comision_admin
    if args.docente is not None: params.docente_usd = args.docente
    if args.usd_pen is not None: params.usd_pen = args.usd_pen

    pnl = compute_pnl(baseline, params, ingreso_mode=args.ingreso)

    header = (
        f"\n>>> Producto {pid}: {kpis['Nombre']}\n"
        f">>> Leads={baseline.leads:,} · Asesores={kpis['AsesoresInvolucrados']} (FTE={fte:.2f}) · "
        f"Matric={baseline.matriculados} · Comprometido=${baseline.monto_comprometido_usd:,.2f} · "
        f"Cobrado=${baseline.monto_cobrado_usd:,.2f}\n"
        f">>> Parámetros: salario={params.salario_base_pen} PEN · CPL=${params.cpl_usd} · "
        f"comAs={params.comision_asesor_pct*100:.0f}% · comAdm={params.comision_admin_pct*100:.0f}% · "
        f"docente=${params.docente_usd} · USD/PEN={params.usd_pen}\n"
        f">>> Ingreso = {args.ingreso} · Moneda = {args.moneda.upper()}\n"
    )
    print(header, file=sys.stderr)

    # Los montos de pnl.* están en PEN. Con --moneda usd se dividen por USD/PEN.
    div = params.usd_pen if args.moneda == "usd" else 1.0
    def m(x):  # convierte un monto PEN a la moneda elegida
        return round(x / div, 2)
    col = "Valor_USD" if args.moneda == "usd" else "Valor_PEN"

    rows = [
        {"Concepto": "Salarios proporcionales", col: m(pnl.salarios)},
        {"Concepto": "Docentes", col: m(pnl.docentes)},
        {"Concepto": "CPL", col: m(pnl.cpl)},
        {"Concepto": "Comisión asesores", col: m(pnl.comision_asesores)},
        {"Concepto": "Admin", col: m(pnl.admin)},
        {"Concepto": "COSTO TOTAL", col: m(pnl.costo_total)},
        {"Concepto": "Ingreso", col: m(pnl.ingreso_pen)},
        {"Concepto": "MARGEN", col: m(pnl.margen_pen)},
        {"Concepto": "Margen %", col: round(pnl.margen_pct * 100, 2)},
        {"Concepto": "Costo / lead", col: m(pnl.costo_por_lead)},
        {"Concepto": "Costo / matrícula", col: m(pnl.costo_por_matricula)},
        {"Concepto": "Ingreso / matrícula", col: m(pnl.ingreso_por_matricula)},
        {"Concepto": "Break-even TC (%)", col: round(pnl.breakeven_tc * 100, 3) if pnl.breakeven_tc else None},
        {"Concepto": "CPL máx rentable (USD)", col: round(pnl.breakeven_cpl_usd, 4) if pnl.breakeven_cpl_usd else None},
    ]
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
