#!/usr/bin/env python3
"""
P&L y análisis de sensibilidad para un producto.

PROTOCOLO (igual que el forecast): el CPL y el pago docente son datos que DEBE
dar el usuario para este curso — no se asumen defaults silenciosamente. Sin
`--cpl` y `--docente` el script sale con exit 3 y el mensaje de qué preguntar.

Uso:
  python scripts/producto_pnl.py imbpepkeyacc05261 --cpl 0.25 --docente 1440
  python scripts/producto_pnl.py 381 --cpl 0.25 --docente 1440      # por Id interno
  python scripts/producto_pnl.py imbpepkeyacc05261 --cpl 0.25 --docente 1440 --ingreso comprometido
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cli, db, queries
from lib.calc import CostParams, ProductBaseline, compute_pnl, fte_equivalents
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="P&L de un producto con análisis de sensibilidad")
    ap.add_argument("producto", help="CodigoLanzamiento del curso (preferido) o Id interno")
    ap.add_argument("--ingreso", choices=["cobrado", "comprometido"], default="cobrado")
    ap.add_argument("--salario", type=float, help="Override salario base PEN")
    ap.add_argument("--cpl", type=float, help="CPL en USD por lead (OBLIGATORIO: preguntar al usuario)")
    ap.add_argument("--comision-asesor", type=float, help="Override comisión asesor (0.10 = 10%%)")
    ap.add_argument("--comision-admin", type=float, help="Override comisión admin")
    ap.add_argument("--docente", type=float, help="Pago docente en USD por curso (OBLIGATORIO: preguntar al usuario)")
    ap.add_argument("--usd-pen", type=float, help="Override tipo de cambio USD->PEN")
    ap.add_argument("--moneda", choices=["usd", "pen"], default="usd",
                    help="Moneda de las columnas de plata del P&L. 'usd' (DEFAULT): convierte "
                         "los montos PEN a USD dividiendo por USD/PEN. 'pen': montos en soles. "
                         "Los ratios (Margen %%, Break-even TC) y el CPL máx (ya en USD) no cambian.")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    # El CPL y el pago docente varían por curso y los conoce el usuario; correr
    # con los defaults de config.toml da un P&L engañoso sin que se note.
    faltan = []
    if args.cpl is None:
        faltan.append("CPL real del curso en USD por lead (--cpl)")
    if args.docente is None:
        faltan.append("pago docente del curso en USD (--docente)")
    if faltan:
        print("FALTAN DATOS DEL USUARIO para el P&L:", file=sys.stderr)
        for f in faltan:
            print(f"  - {f}", file=sys.stderr)
        print("Pregúntale estos valores al usuario y reintenta pasándolos como flags.",
              file=sys.stderr)
        sys.exit(3)

    prod = cli.resolver_producto(args.producto)
    pid, codigo = prod["Id"], prod["Codigo"] or f"(sin código, id interno {prod['Id']})"

    # KPIs base del producto
    kpis = db.query_one(queries.SQL_PRODUCT_KPIS, [pid, pid, pid, pid, pid, pid, pid])
    if not kpis or not kpis.get("TotalLeads"):
        print(f"Producto {codigo} no encontrado o sin leads.", file=sys.stderr)
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
        f"\n>>> Curso {codigo} · {kpis['Nombre']}\n"
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
    def m(x):  # convierte un monto PEN a la moneda elegida (None = sin dato)
        return round(x / div, 2) if x is not None else None
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
