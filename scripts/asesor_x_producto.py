#!/usr/bin/env python3
"""
Productos en los que vende mejor un asesor.

Para un IdPersonal específico, lista todos los productos donde tuvo leads en
el período y muestra leads, matrículas, TC y Wilson LB 95%. Ordenado por
Wilson LB descendente (para que aparezcan arriba los productos con la mejor
conversión bien establecida, no los con muestra chica).

Atribución: usa la misma lógica que el resto de scripts (`IdPersonal` en
`HistorialEstado`, dedup por `IdOportunidad`, soft-delete en joins). El cobrado
USD se suma sobre las oportunidades que ESE asesor matriculó (IdEstado=3).

Uso:
  python scripts/asesor_x_producto.py 81
  python scripts/asesor_x_producto.py 81 --periodo 90
  python scripts/asesor_x_producto.py 81 --periodo 365 --min-leads 10
  python scripts/asesor_x_producto.py 81 --fmt csv -o asesor81_productos.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.calc import wilson_lb
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="Productos en los que un asesor vende mejor")
    ap.add_argument("asesor_id", type=int, help="IdPersonal del asesor")
    ap.add_argument("--periodo", type=int, default=90, help="Días hacia atrás (default 90)")
    ap.add_argument("--min-leads", type=int, default=5, help="Mostrar sólo productos con >= N leads (default 5)")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    aid = args.asesor_id
    p = args.periodo

    # Confirm asesor exists (and grab name for the header)
    info = db.query_one(
        "SELECT LTRIM(RTRIM(ISNULL(p.Nombres,'')+' '+ISNULL(p.Apellidos,''))) AS Nombre "
        "FROM adm.Personal p WHERE p.Id = ? AND p.Estado = 1",
        [aid],
    )
    if not info:
        print(f"Asesor {aid} no encontrado o inactivo.", file=sys.stderr)
        sys.exit(1)

    leads_rows = db.query(queries.SQL_LEADS_ASESOR_X_PRODUCTO, [aid, p])
    matric_rows = db.query(queries.SQL_MATRIC_ASESOR_X_PRODUCTO, [aid, p])
    cobrado_rows = db.query(queries.SQL_COBRADO_ASESOR_X_PRODUCTO, [aid, p])

    matric_by_prod = {r["IdProducto"]: int(r["Matric"]) for r in matric_rows}
    cobrado_by_prod = {r["IdProducto"]: float(r["CobradoUSD"] or 0) for r in cobrado_rows}

    rows = []
    for r in leads_rows:
        pid = r["IdProducto"]
        leads = int(r["Leads"])
        if leads < args.min_leads:
            continue
        matric = matric_by_prod.get(pid, 0)
        cobrado = cobrado_by_prod.get(pid, 0.0)
        tc = (matric / leads) if leads else 0.0
        w = wilson_lb(matric, leads)
        rows.append({
            "Codigo": (r["Codigo"] or "").strip() or f"id:{pid}",
            "Producto": r["Producto"],
            "Leads": leads,
            "Matric": matric,
            "TC%": round(tc * 100, 2),
            "WilsonLB%": round(w * 100, 2),
            "$Cobrado_USD": round(cobrado, 2),
        })

    rows.sort(key=lambda r: -r["WilsonLB%"])
    print(
        f"\n>>> {info['Nombre']} (#{aid}) · período {p} días · {len(rows)} productos con >= {args.min_leads} leads\n",
        file=sys.stderr,
    )
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
