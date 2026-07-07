#!/usr/bin/env python3
"""
Detalle de un asesor: información general, leads, llamadas, matrículas, time-to-first-sale, funnel.

Uso:
  python scripts/asesor_detail.py 81                  # último período de 90 días
  python scripts/asesor_detail.py 81 --periodo 30
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
    ap = argparse.ArgumentParser(description="Detalle de un asesor")
    ap.add_argument("asesor_id", type=int)
    ap.add_argument("--periodo", type=int, default=90)
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    aid = args.asesor_id
    p = args.periodo

    info = db.query_one(
        "SELECT p.Id, LTRIM(RTRIM(ISNULL(p.Nombres,'')+' '+ISNULL(p.Apellidos,''))) AS Nombre, "
        "p.IdTipoJornada, p.FechaIngreso, ISNULL(pa.Nombre,'') AS Pais "
        "FROM adm.Personal p LEFT JOIN mdm.Pais pa ON pa.Id=p.IdPais "
        "WHERE p.Id=? AND p.Estado=1",
        [aid],
    )
    if not info:
        print(f"Asesor {aid} no encontrado o inactivo.", file=sys.stderr)
        sys.exit(1)

    def solo_asesor(sql: str) -> dict:
        return db.query_one(queries.sql_filtrar_asesor(sql), [p, aid]) or {}

    leads = solo_asesor(queries.SQL_LEADS_ASIGNADOS).get("LeadsAsignados", 0)
    matric = solo_asesor(queries.SQL_MATRICULAS_POR_ASESOR).get("Matriculas", 0)
    ll = solo_asesor(queries.SQL_LLAMADAS_POR_ASESOR)
    comp = float(solo_asesor(queries.SQL_COBRANZA_COMPROMETIDA).get("ComprometidoUSD") or 0)
    cobr = float(solo_asesor(queries.SQL_COBRANZA_COBRADA).get("CobradoUSD") or 0)

    tc = (matric / leads) if leads else None
    w = wilson_lb(matric, leads)

    print(
        f"\n>>> {info['Nombre']} (#{aid}) · jornada={'TC' if info['IdTipoJornada']==31 else 'TP'} · país={info['Pais']} · ingresó {info['FechaIngreso']}\n"
        f">>> Período: {p} días\n",
        file=sys.stderr,
    )

    rows = [
        {"Metric": "Leads asignados", "Valor": leads},
        {"Metric": "Llamadas contestadas", "Valor": ll.get("Contestadas", 0) or 0},
        {"Metric": "Llamadas no contestadas", "Valor": ll.get("NoContestadas", 0) or 0},
        {"Metric": "Días activos", "Valor": ll.get("DiasActivos", 0) or 0},
        {"Metric": "Matriculaciones", "Valor": matric},
        {"Metric": "TC", "Valor": round(tc * 100, 2) if tc is not None else "—"},
        {"Metric": "Wilson LB 95%", "Valor": round(w * 100, 2)},
        {"Metric": "Comprometido USD", "Valor": round(comp, 2)},
        {"Metric": "Cobrado USD", "Valor": round(cobr, 2)},
    ]
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
