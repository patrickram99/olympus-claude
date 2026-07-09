#!/usr/bin/env python3
"""
Comparar el P&L de varios productos en una sola tabla.

Acepta una lista de cursos (CodigoLanzamiento preferido, o Id interno) y muestra
una fila por producto con los KPIs clave (Leads, Matric, FTE, CostoTotal,
Ingreso, Margen, Margen%). Permite override de los mismos parámetros que
`producto_pnl.py` — se aplican por igual a todos los productos comparados.

Comparte 100% de la lógica de cómputo con `producto_pnl.py` vía `lib.calc`,
para que los números sean consistentes.

Uso:
  python scripts/producto_compare.py imbpepkeyacc05261 imbcepgeshum07261
  python scripts/producto_compare.py 381 382 --ingreso comprometido
  python scripts/producto_compare.py 381 382 --cpl 0.30 --usd-pen 3.85
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
    ap = argparse.ArgumentParser(description="Comparar P&L de varios productos")
    ap.add_argument("productos", nargs="+",
                    help="Cursos a comparar: CodigoLanzamiento (preferido) o Id interno")
    ap.add_argument("--ingreso", choices=["cobrado", "comprometido"], default="cobrado")
    ap.add_argument("--salario", type=float, help="Override salario base PEN")
    ap.add_argument("--cpl", type=float, help="Override CPL USD")
    ap.add_argument("--comision-asesor", type=float, help="Override comisión asesor (0.10 = 10%%)")
    ap.add_argument("--comision-admin", type=float, help="Override comisión admin")
    ap.add_argument("--docente", type=float, help="Override costo docente USD")
    ap.add_argument("--usd-pen", type=float, help="Override tipo de cambio USD->PEN")
    ap.add_argument("--moneda", choices=["usd", "pen"], default="usd",
                    help="Moneda de las columnas de plata (Costo/Ingreso/Margen). 'usd' (DEFAULT): "
                         "convierte de PEN a USD dividiendo por USD/PEN. 'pen': montos en soles. "
                         "Margen%% y TC%% no cambian.")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    # Build the (single) parameter set — applied to every product.
    params = CostParams.from_env()
    if args.salario is not None: params.salario_base_pen = args.salario
    if args.cpl is not None: params.cpl_usd = args.cpl
    if args.comision_asesor is not None: params.comision_asesor_pct = args.comision_asesor
    if args.comision_admin is not None: params.comision_admin_pct = args.comision_admin
    if args.docente is not None: params.docente_usd = args.docente
    if args.usd_pen is not None: params.usd_pen = args.usd_pen

    # Total leads por asesor (constante para todos los productos en el mismo período/all-time).
    # Lo calculamos una sola vez para amortizar IO.
    leads_tot = {r["IdPersonal"]: r["LeadsTotal"] for r in db.query(queries.SQL_LEADS_TOTAL_POR_ASESOR)}

    # Los montos de pnl.* están en PEN. Con --moneda usd se dividen por USD/PEN.
    div = params.usd_pen if args.moneda == "usd" else 1.0
    suf = "USD" if args.moneda == "usd" else "PEN"
    c_costo, c_ing, c_marg = f"Costo_{suf}", f"Ingreso_{suf}", f"Margen_{suf}"

    rows = []
    missing: list[str] = []
    for valor in args.productos:
        prod = cli.resolver_producto(valor)
        pid = prod["Id"]
        codigo = prod["Codigo"] or f"(id interno {pid})"
        kpis = db.query_one(queries.SQL_PRODUCT_KPIS, [pid, pid, pid, pid, pid, pid, pid])
        if not kpis or not kpis.get("TotalLeads"):
            missing.append(codigo)
            continue

        leads_prod = {r["IdPersonal"]: r["LeadsProducto"] for r in db.query(queries.SQL_LEADS_PRODUCTO_POR_ASESOR, [pid])}
        fte = fte_equivalents(leads_prod, leads_tot)

        baseline = ProductBaseline(
            leads=int(kpis["TotalLeads"]),
            matriculados=int(kpis["Matriculados"] or 0),
            fte=fte,
            monto_comprometido_usd=float(kpis["MontoComprometidoUSD"] or 0),
            monto_cobrado_usd=float(kpis["MontoCobradoUSD"] or 0),
            costo_base_usd=float(kpis["CostoBaseUSD"] or 0),
        )
        pnl = compute_pnl(baseline, params, ingreso_mode=args.ingreso)

        rows.append({
            "Codigo": codigo,
            "Producto": (kpis["Nombre"] or "")[:50],
            "FTE": round(fte, 2),
            "Leads": baseline.leads,
            "Matric": baseline.matriculados,
            "TC%": round((baseline.matriculados / baseline.leads * 100) if baseline.leads else 0, 2),
            c_costo: round(pnl.costo_total / div, 2),
            c_ing: round(pnl.ingreso_pen / div, 2),
            c_marg: round(pnl.margen_pen / div, 2),
            "Margen%": round(pnl.margen_pct * 100, 2),
        })

    # Sort by margen desc — winners first.
    rows.sort(key=lambda r: -r[c_marg])

    header = (
        f"\n>>> Comparando {len(rows)} productos · ingreso={args.ingreso} · moneda={args.moneda.upper()}\n"
        f">>> Parámetros: salario={params.salario_base_pen} PEN · CPL=${params.cpl_usd} · "
        f"comAs={params.comision_asesor_pct*100:.0f}% · comAdm={params.comision_admin_pct*100:.0f}% · "
        f"docente=${params.docente_usd} · USD/PEN={params.usd_pen}\n"
    )
    if missing:
        header += f">>> WARN: no encontrados o sin leads: {missing}\n"
    print(header, file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
