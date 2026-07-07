#!/usr/bin/env python3
"""
Ranking de asesores con Wilson lower bound 95%.

Uso:
  python scripts/asesores_top.py [--periodo 30] [--umbral 30] [--jornada 31|32] [--top 20] [-o out.csv]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cli, db, queries
from lib.calc import wilson_lb, wilson_ub
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="Ranking de asesores por TC (Wilson LB)")
    ap.add_argument("--periodo", type=int, default=30, help="Días hacia atrás (default 30)")
    ap.add_argument("--umbral", type=int, default=30, help="Umbral mínimo de leads (default 30)")
    ap.add_argument("--jornada", type=int, choices=[31, 32], help="Filtrar jornada")
    ap.add_argument("--top", type=cli.top_type, default=20, help="N asesores a mostrar (default 20)")
    ap.add_argument("--bottom", action="store_true", help="Mostrar bottom en vez de top")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    args = ap.parse_args()

    p = args.periodo

    ases = {a["Id"]: a for a in db.query(queries.SQL_ASESORES_ACTIVOS)}
    leads = {r["IdPersonal"]: r["LeadsAsignados"] for r in db.query(queries.SQL_LEADS_ASIGNADOS, [p])}
    matric = {r["IdPersonal"]: r["Matriculas"] for r in db.query(queries.SQL_MATRICULAS_POR_ASESOR, [p])}
    llamadas = {r["IdPersonal"]: r for r in db.query(queries.SQL_LLAMADAS_POR_ASESOR, [p])}
    comprometido = {r["IdPersonal"]: float(r["ComprometidoUSD"] or 0) for r in db.query(queries.SQL_COBRANZA_COMPROMETIDA, [p])}
    cobrado = {r["IdPersonal"]: float(r["CobradoUSD"] or 0) for r in db.query(queries.SQL_COBRANZA_COBRADA, [p])}

    rows = []
    for aid, info in ases.items():
        if args.jornada and info["Jornada"] != args.jornada:
            continue
        l = leads.get(aid, 0)
        m = matric.get(aid, 0)
        call = llamadas.get(aid, {})
        ll_c = call.get("Contestadas", 0) or 0
        ll_n = call.get("NoContestadas", 0) or 0
        dias = call.get("DiasActivos", 0) or 0
        ll = ll_c + ll_n
        tc = m / l if l else None
        w = wilson_lb(m, l)
        wu = wilson_ub(m, l)
        rows.append({
            "Id": aid,
            "Asesor": info["Nombre"],
            "Jornada": "TC" if info["Jornada"] == 31 else "TP",
            "Leads": l,
            "Matric": m,
            "Llamadas": ll,
            "DiasActivos": dias,
            "LeadsxVenta": round(l / m, 1) if m else "∞",
            "TC": round(tc * 100, 2) if tc is not None else None,
            "WilsonLB%": round(w * 100, 2),
            "WilsonUB%": round(wu * 100, 2),
            "$Comp_USD": round(comprometido.get(aid, 0), 2),
            "$Cobrado_USD": round(cobrado.get(aid, 0), 2),
        })

    # Filtrar por umbral
    elig = [r for r in rows if r["Leads"] >= args.umbral]
    if args.bottom:
        # "Menos eficientes": ordenar por Wilson UPPER bound ascendente. El LB deja a
        # todos los de 0 matrículas empatados en 0,0 sin importar el volumen, así que la
        # lista se llena de ceros y esconde a los ineficientes de alto volumen (mucho
        # lead quemado con poca/ninguna venta). El UB sí los distingue: 0/1376 tiene un
        # UB mucho menor que 0/30, así que quien más desperdició sube al tope. Empate →
        # más leads primero (peor). Se muestra el ranking de peor a mejor.
        elig.sort(key=lambda r: (r["WilsonUB%"], -r["Leads"]))
        result = elig[: args.top]
    else:
        elig.sort(key=lambda r: -r["WilsonLB%"])
        result = elig[: args.top]

    orden = "menos eficientes (Wilson UB asc)" if args.bottom else "mejores (Wilson LB desc)"
    print(f"\n>>> Período: {p} días · umbral mínimo: {args.umbral} leads · {len(elig)} asesores elegibles · orden: {orden}\n", file=sys.stderr)
    output(result, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
