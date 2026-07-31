#!/usr/bin/env python3
"""
Reporte completo de UN curso por su CodigoLanzamiento (o Id interno): ficha,
captación de leads, foto actual del funnel, esfuerzo comercial e ingresos.

SIEMPRE all-time: cubre TODAS las oportunidades asignadas al curso, sin
ventanas móviles (pedido explícito del usuario 2026-07-23 — un reporte de
curso no lleva métricas de "últimos N días").

Consolida en una sola corrida lo que antes requería product_search.py +
funnel_estado.py + queries ad-hoc de fechas de captación y cobranza. Para la
foto del funnel de un curso a secas sigue existiendo funnel_estado.py; para
P&L/margen usar producto_pnl.py (pide CPL y docente al usuario).

- Funnel = último HistorialEstado por oportunidad (stock actual, no flujo).
- Llamadas = último valor acumulado por oportunidad (los contadores son
  running totals), sumado sobre todas las oportunidades del curso.
- Ingresos = cohorte all-time del curso: comprometido (CobranzaPlan.Total de
  las matriculadas) y cobrado (CobranzaPago). USD por defecto (--moneda pen).
- FechaInicio: la de adm.Producto; si es NULL se infiere del sufijo MMYYN del
  CodigoLanzamiento (p.ej. ...07261 -> 2026-07) y se marca como inferida.

Uso:
  python scripts/curso_report.py imbpepkeyacc05261     # por código (preferido)
  python scripts/curso_report.py 400                   # por Id interno
  python scripts/curso_report.py imbpepkeyacc05261 --moneda pen
  python scripts/curso_report.py imbpepkeyacc05261 --fmt csv -o reporte.csv
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

# Sufijo MMYYN del CodigoLanzamiento (p.ej. imbpepkeyacc05261 -> 05/26 rel 1).
_SUFIJO_RE = re.compile(r"(\d{2})(\d{2})\d$")

SQL_FICHA = """
SELECT pr.Id,
  ISNULL(pr.CodigoLanzamiento, '') AS Codigo,
  LTRIM(RTRIM(pr.Nombre)) AS Nombre,
  pr.CostoBase,
  pr.EstadoProductoTipoId,
  ISNULL(t.Nombre, '') AS EstadoCatalogo,
  CONVERT(varchar(10), pr.FechaInicio, 23) AS FechaInicio,
  CONVERT(varchar(10), pr.FechaFin, 23) AS FechaFin,
  LTRIM(RTRIM(ISNULL(per.Nombres, '') + ' ' + ISNULL(per.Apellidos, ''))) AS Desarrollador
FROM adm.Producto pr
LEFT JOIN adm.Tipo t ON t.Id = pr.EstadoProductoTipoId
LEFT JOIN adm.Personal per ON per.Id = pr.PersonalCreacion AND per.Estado = 1
WHERE pr.Estado = 1 AND pr.Id = ?
"""

SQL_CAPTACION = """
SELECT
  CONVERT(varchar(10), MIN(op.FechaCreacion), 23) AS PrimerLead,
  CONVERT(varchar(10), MAX(op.FechaCreacion), 23) AS UltimoLead,
  COUNT(*) AS Leads
FROM adm.Oportunidad op
WHERE op.Estado = 1 AND op.IdProducto = ?
"""

# Contadores de llamadas son acumulados por oportunidad: tomar la última fila
# (rn=1 desc) de cada una y sumar.
SQL_LLAMADAS = """
SELECT SUM(cur.C) AS Contestadas, SUM(cur.NC) AS NoContestadas
FROM (
  SELECT he.CantidadLlamadasContestadas AS C, he.CantidadLlamadasNoContestadas AS NC,
    ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion DESC, he.Id DESC) AS rn
  FROM adm.HistorialEstado he
  INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
    AND op.IdProducto = ?
  WHERE he.Estado = 1
) cur
WHERE cur.rn = 1
"""

ESTADOS = [
    (1, "Registrado"), (4, "Calificado"), (5, "Potencial"), (6, "Promesa"),
    (3, "Matriculado (Ins)"), (7, "Perdido"), (2, "No calificado"),
]


def fecha_inicio(ficha: dict) -> str:
    """FechaInicio de la BD, o inferida del sufijo MMYYN del código."""
    if ficha["FechaInicio"]:
        return ficha["FechaInicio"]
    m = _SUFIJO_RE.search(ficha["Codigo"] or "")
    if m:
        mes, anio = m.groups()
        return f"20{anio}-{mes} (inferida del código)"
    return "—"


def main():
    ap = argparse.ArgumentParser(description="Reporte completo de un curso por CodigoLanzamiento.")
    ap.add_argument("producto", help="CodigoLanzamiento del curso (preferido) o Id interno.")
    ap.add_argument("--usd-pen", type=float,
                    help="Tipo de cambio USD->PEN (default: config.toml). Solo aplica con --moneda pen.")
    cli.add_moneda(ap)
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    usd_pen = args.usd_pen if args.usd_pen is not None else CostParams.from_env().usd_pen
    factor, suf = cli.factor_moneda(args.moneda, usd_pen)

    prod = cli.resolver_producto(args.producto)
    pid = prod["Id"]

    ficha = db.query_one(SQL_FICHA, [pid])
    capta = db.query_one(SQL_CAPTACION, [pid]) or {}
    llam = db.query_one(SQL_LLAMADAS, [pid]) or {}
    kpis = db.query_one(queries.SQL_PRODUCT_KPIS, [pid] * 7) or {}
    funnel = db.query(queries.SQL_FUNNEL_ESTADO_ACTUAL, [pid, pid])

    counts = {int(r["IdEstado"]): int(r["N"]) for r in funnel}
    total = sum(counts.values())
    ins = counts.get(3, 0)
    reg = counts.get(1, 0)
    activos = sum(counts.get(e, 0) for e in (1, 4, 5, 6))
    perdidos = counts.get(7, 0) + counts.get(2, 0)
    procesados = total - reg

    compr = float(kpis.get("MontoComprometidoUSD") or 0)
    cobr = float(kpis.get("MontoCobradoUSD") or 0)

    print(f"\n>>> REPORTE DE CURSO · {ficha['Codigo'] or '(sin código)'} · {ficha['Nombre']}"
          f"  ·  moneda={suf}" + (f"  ·  USD/PEN={usd_pen}" if args.moneda == "pen" else ""),
          file=sys.stderr)
    print(f">>> Estado catálogo: {ficha['EstadoCatalogo'] or ficha['EstadoProductoTipoId']}"
          f" · Desarrollador: {ficha['Desarrollador'] or '(sin encargado)'}"
          f" · Inicio: {fecha_inicio(ficha)}\n", file=sys.stderr)

    def pct(n: int, d: int) -> float | str:
        return round(n / d * 100, 2) if d else "—"

    rows = [
        {"Seccion": "Ficha", "Metric": "Curso", "Valor": ficha["Nombre"]},
        {"Seccion": "Ficha", "Metric": "Desarrollador", "Valor": ficha["Desarrollador"] or "(sin encargado)"},
        {"Seccion": "Ficha", "Metric": "Estado catálogo", "Valor": ficha["EstadoCatalogo"] or str(ficha["EstadoProductoTipoId"])},
        {"Seccion": "Ficha", "Metric": f"Precio base {suf}", "Valor": round(float(ficha["CostoBase"] or 0) * factor, 2)},
        {"Seccion": "Ficha", "Metric": "Fecha inicio", "Valor": fecha_inicio(ficha)},
        {"Seccion": "Captación", "Metric": "Primer lead", "Valor": capta.get("PrimerLead") or "—"},
        {"Seccion": "Captación", "Metric": "Último lead", "Valor": capta.get("UltimoLead") or "—"},
        {"Seccion": "Captación", "Metric": "Leads totales", "Valor": int(capta.get("Leads") or 0)},
    ]
    for estado, nombre in ESTADOS:
        rows.append({"Seccion": "Funnel actual", "Metric": nombre,
                     "Valor": counts.get(estado, 0)})
    rows += [
        {"Seccion": "Funnel actual", "Metric": "Activos (Reg/Cal/Pot/Prom)", "Valor": activos},
        {"Seccion": "Funnel actual", "Metric": "Perdidos + No calificados", "Valor": perdidos},
        {"Seccion": "Funnel actual", "Metric": "TC actual % (Ins/Leads)", "Valor": pct(ins, total)},
        {"Seccion": "Funnel actual", "Metric": "TCProc % (Ins/procesados)", "Valor": pct(ins, procesados)},
        {"Seccion": "Esfuerzo", "Metric": "Asesores involucrados", "Valor": int(kpis.get("AsesoresInvolucrados") or 0)},
        {"Seccion": "Esfuerzo", "Metric": "Llamadas contestadas", "Valor": int(llam.get("Contestadas") or 0)},
        {"Seccion": "Esfuerzo", "Metric": "Llamadas no contestadas", "Valor": int(llam.get("NoContestadas") or 0)},
        {"Seccion": "Ingresos", "Metric": f"Comprometido {suf}", "Valor": round(compr * factor, 2)},
        {"Seccion": "Ingresos", "Metric": f"Cobrado {suf}", "Valor": round(cobr * factor, 2)},
        {"Seccion": "Ingresos", "Metric": "% Cobrado", "Valor": pct(cobr, compr) if compr else "—"},
    ]
    output(rows, fmt=args.fmt, out_path=args.output)

    if total == 0:
        print("\n(sin oportunidades registradas para este curso)", file=sys.stderr)


if __name__ == "__main__":
    main()
