# -*- coding: utf-8 -*-
"""
Forecast GP + break-even de UN programa (curso en venta).

Proyecta con Gaussian Processes (GPyTorch) los leads de la próxima semana y
las ventas acumuladas al deadline (fecha de inicio), calcula el punto de
break-even y recomienda CONTINUAR / RIESGO / CANCELAR + leads/semana a solicitar.

Uso:
  python scripts/forecast_programa.py --codigo imbpepkeyacc05261 --cpl 5.0 --docente 5443
  python scripts/forecast_programa.py --codigo 408 --cpl 5.0 --docente 5443 --fecha-inicio 2026-09-01

Datos que el usuario DEBE aportar (el script sale con código 3 si faltan):
  --cpl           costo por lead en PEN
  --docente       costo docente de la cohorte en PEN
  --fecha-inicio  solo si no se puede derivar de la BD ni del CodigoLanzamiento

Break-even: bruto - 11% comisiones - 10% admin = ticket neto; por venta se
descuentan CAC de asesor (calculado en runtime por jornada PT/FT) y CPL/TC;
el docente es el costo fijo: N_BE = ceil(docente / margen_por_venta).
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db  # noqa: E402
from lib import queries  # noqa: E402
from lib.format import fmt_money, fmt_pct, output  # noqa: E402

# El forecast GP es una capa aparte con dependencias pesadas (torch/gpytorch).
try:
    from lib import forecast_gp as fg  # noqa: E402
except ImportError:
    print(
        "ERROR: faltan las dependencias del forecast (capa opcional). "
        "Instala con: pip install -r requirements-forecast.txt",
        file=sys.stderr,
    )
    sys.exit(2)

TICKET_FLOOR_USD = 10.0
TICKET_CAP_USD = 5000.0
VENTANA_CAC_DIAS = 30

SQL_PRODUCTO = """
SELECT pr.Id, LTRIM(RTRIM(pr.Nombre)) AS Nombre, ISNULL(pr.CodigoLanzamiento,'') AS Codigo, pr.CostoBase,
       CONVERT(varchar(10), pr.FechaInicio, 23) AS FechaInicio,
       LTRIM(RTRIM(ISNULL(per.Nombres,'') + ' ' + ISNULL(per.Apellidos,''))) AS Desarrollador,
       pr.EstadoProductoTipoId
FROM adm.Producto pr
LEFT JOIN adm.Personal per ON per.Id = pr.PersonalCreacion AND per.Estado = 1
WHERE pr.Estado = 1 AND (pr.Id = ? OR pr.CodigoLanzamiento = ?)
"""

# Series DIARIAS: los leads y ventas entran en tiempo real, el GP trabaja por día
SQL_LEADS_DIARIOS = """
SELECT CAST(op.FechaCreacion AS date) AS Dia, COUNT(DISTINCT op.Id) AS N
FROM adm.Oportunidad op
WHERE op.Estado = 1 AND op.IdProducto = ?
GROUP BY CAST(op.FechaCreacion AS date)
ORDER BY Dia
"""

# Primera fila IdEstado=3 por oportunidad (P8: evita matrículas duplicadas)
SQL_VENTAS_DIARIAS = """
SELECT CAST(q.FMat AS date) AS Dia, COUNT(*) AS N
FROM (
  SELECT he.IdOportunidad, MIN(he.FechaCreacion) AS FMat
  FROM adm.HistorialEstado he
  INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
  WHERE he.Estado = 1 AND he.IdEstado = 3 AND op.IdProducto = ?
  GROUP BY he.IdOportunidad
) q
GROUP BY CAST(q.FMat AS date)
ORDER BY Dia
"""

# CobranzaPlan.IdProducto es NULL en la BD: ir vía Oportunidad
SQL_TICKETS = """
SELECT cp.Total
FROM adm.CobranzaPlan cp
INNER JOIN adm.Oportunidad op ON op.Id = cp.IdOportunidad AND op.Estado = 1
WHERE cp.Estado = 1 AND op.IdProducto = ? AND cp.Total BETWEEN ? AND ?
"""

# Performance de los RELANZAMIENTOS previos del mismo código de marketing
# (base sin sufijo MMYY+release): primeros 45 días de cada lanzamiento.
SQL_RELANZAMIENTOS_45D = """
SELECT COUNT(DISTINCT op.Id) AS Leads,
       COUNT(DISTINCT CASE WHEN w.FMat IS NOT NULL
                            AND w.FMat < DATEADD(day, 45, f.F0) THEN op.Id END) AS Ventas,
       COUNT(DISTINCT pr.Id) AS Lanzamientos
FROM adm.Oportunidad op
INNER JOIN adm.Producto pr ON pr.Id = op.IdProducto AND pr.Estado = 1
INNER JOIN (SELECT IdProducto, MIN(FechaCreacion) AS F0
            FROM adm.Oportunidad WHERE Estado = 1 GROUP BY IdProducto) f
  ON f.IdProducto = op.IdProducto
LEFT JOIN (SELECT IdOportunidad, MIN(FechaCreacion) AS FMat
           FROM adm.HistorialEstado WHERE Estado = 1 AND IdEstado = 3
           GROUP BY IdOportunidad) w ON w.IdOportunidad = op.Id
WHERE op.Estado = 1 AND LOWER(ISNULL(pr.CodigoLanzamiento,'')) LIKE ?
  AND pr.Id <> ? AND op.FechaCreacion < DATEADD(day, 45, f.F0)
"""

# Estado ACTUAL del funnel del producto (última fila de HistorialEstado por oportunidad)
SQL_FUNNEL_ESTADO = """
SELECT q.IdEstado, COUNT(*) AS N
FROM (
  SELECT he.IdOportunidad, he.IdEstado,
         ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad
                            ORDER BY he.FechaCreacion DESC, he.Id DESC) AS rn
  FROM adm.HistorialEstado he
  INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
  WHERE he.Estado = 1 AND op.IdProducto = ?
) q
WHERE q.rn = 1
GROUP BY q.IdEstado
"""

# TC agregada de la familia (fallback cuando el producto no tiene muestra propia)
SQL_TC_FAMILIA = """
SELECT COUNT(DISTINCT op.Id) AS Leads, COUNT(DISTINCT w.IdOportunidad) AS Ventas
FROM adm.Oportunidad op
INNER JOIN adm.Producto pr ON pr.Id = op.IdProducto AND pr.Estado = 1
LEFT JOIN (SELECT DISTINCT IdOportunidad FROM adm.HistorialEstado
           WHERE IdEstado = 3 AND Estado = 1) w ON w.IdOportunidad = op.Id
WHERE op.Estado = 1 AND LOWER(ISNULL(pr.CodigoLanzamiento,'')) LIKE ?
"""


def resolver_producto(codigo: str) -> dict:
    pid = int(codigo) if codigo.isdigit() else -1
    row = db.query_one(SQL_PRODUCTO, [pid, codigo])
    if not row:
        print(f"ERROR: no se encontró producto activo con código/Id '{codigo}'. "
              f"Usa scripts/product_search.py para buscarlo.", file=sys.stderr)
        sys.exit(1)
    return row


def cac_runtime(p: fg.BreakevenParams) -> dict:
    """CAC por jornada con llamadas (delta clampado) y matrículas de los últimos 30 días."""
    asesores = {r["Id"]: r["Jornada"] for r in db.query(queries.SQL_ASESORES_ACTIVOS)}
    llamadas = db.query(queries.SQL_LLAMADAS_POR_ASESOR, [VENTANA_CAC_DIAS])
    matric = db.query(queries.SQL_MATRICULAS_POR_ASESOR, [VENTANA_CAC_DIAS])

    tot_llam = {31: 0, 32: 0}
    asesores_con_llam = {31: 0, 32: 0}
    for r in llamadas:
        j = asesores.get(r["IdPersonal"])
        if j in tot_llam:
            calls = (r["Contestadas"] or 0) + (r["NoContestadas"] or 0)
            if calls > 0:
                tot_llam[j] += calls
                asesores_con_llam[j] += 1
    tot_ventas = {31: 0, 32: 0}
    for r in matric:
        j = asesores.get(r["IdPersonal"])
        if j in tot_ventas:
            tot_ventas[j] += r["Matriculas"] or 0

    res = {}
    for j, sueldo, nombre in ((31, p.sueldo_ft_pen, "FT"), (32, p.sueldo_pt_pen, "PT")):
        llam_mes = tot_llam[j] / asesores_con_llam[j] if asesores_con_llam[j] else 0.0
        llam_x_venta = tot_llam[j] / tot_ventas[j] if tot_ventas[j] else 0.0
        res[nombre] = dict(
            llam_mes=llam_mes, llam_x_venta=llam_x_venta, ventas=tot_ventas[j],
            cac=fg.cac_por_jornada(sueldo, llam_mes, llam_x_venta),
        )
    res["blend"] = fg.cac_blend(res["FT"]["cac"], res["PT"]["cac"],
                                res["FT"]["ventas"], res["PT"]["ventas"])
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description="Forecast GP + break-even de un programa")
    ap.add_argument("--codigo", required=True, help="CodigoLanzamiento o Id del producto")
    ap.add_argument("--cpl", type=float, default=None, help="Costo por lead en PEN")
    ap.add_argument("--docente", type=float, default=None, help="Costo docente de la cohorte en PEN")
    ap.add_argument("--fecha-inicio", default=None, help="YYYY-MM-DD (si la BD no la tiene)")
    ap.add_argument("--optimism", type=float, default=fg.OPTIMISM_Q, help="Cuantil optimista (default 0.95)")
    ap.add_argument("--lookback", type=int, default=None, help="Usar solo los últimos N días")
    ap.add_argument("--min-valid-leads", type=int, default=fg.MIN_VALID_LEADS_DIA,
                    help="Ignorar días con menos leads que esto en el GP de leads (default 15)")
    ap.add_argument("--usd-pen", type=float, default=fg.BreakevenParams.usd_pen)
    args = ap.parse_args()

    prod = resolver_producto(args.codigo)
    deadline = fg.parse_deadline(prod["Codigo"], args.fecha_inicio or prod["FechaInicio"])

    # ---- datos obligatorios: si faltan, salir con código 3 y lista clara ----
    faltantes = []
    if args.cpl is None:
        faltantes.append("--cpl (costo por lead en PEN)")
    if args.docente is None:
        faltantes.append("--docente (costo docente de la cohorte en PEN)")
    if deadline is None:
        faltantes.append("--fecha-inicio (no derivable de FechaInicio ni del CodigoLanzamiento)")
    if faltantes:
        print("FALTAN_DATOS para calcular el forecast de este programa:", file=sys.stderr)
        for f in faltantes:
            print(f"  * {f}", file=sys.stderr)
        sys.exit(3)

    params = fg.BreakevenParams(usd_pen=args.usd_pen)
    hoy = date.today()
    sem_rest = fg.semanas_restantes(deadline, hoy)
    dias_rest = fg.dias_restantes(deadline, hoy)

    # ---- series DIARIAS (los leads/ventas entran en tiempo real; el día de hoy,
    # incompleto, lo excluye prepare_xy; los totales sí incluyen todo) ----
    leads_rows = db.query(SQL_LEADS_DIARIOS, [prod["Id"]])
    ventas_rows = db.query(SQL_VENTAS_DIARIAS, [prod["Id"]])
    leads_total = sum(r["N"] for r in leads_rows)
    ventas_total = sum(r["N"] for r in ventas_rows)

    def _dia(v):
        return v if isinstance(v, date) else v.date()

    l_dates = [_dia(r["Dia"]) for r in leads_rows]
    l_counts = [float(r["N"]) for r in leads_rows]
    v_dates = [_dia(r["Dia"]) for r in ventas_rows]
    v_counts = [float(r["N"]) for r in ventas_rows]

    # ---- ticket ----
    tickets = [float(r["Total"]) for r in db.query(
        SQL_TICKETS, [prod["Id"], TICKET_FLOOR_USD, TICKET_CAP_USD])]
    ticket_usd = statistics.fmean(tickets) if tickets else float(prod["CostoBase"] or 0)
    ticket_fuente = f"CobranzaPlan ({len(tickets)} planes)" if tickets else "CostoBase (sin planes aún)"

    # ---- TC (Wilson LB): relanzamientos 45d > producto > familia ----
    import re as _re
    base = _re.sub(r"\d{5}$", "", (prod["Codigo"] or "").strip().lower()) or None
    rel = None
    if base:
        rel = db.query_one(SQL_RELANZAMIENTOS_45D, [base + "%", prod["Id"]])
        if rel and not rel["Lanzamientos"]:
            rel = None
    familia = fg.parse_familia(prod["Codigo"])
    tc_familia = None
    if familia:
        fam = db.query_one(SQL_TC_FAMILIA, [f"%{familia.lower()}%"])
        if fam and fam["Leads"]:
            tc_familia = (fam["Ventas"], fam["Leads"])
    if rel and (leads_total + rel["Leads"]) >= 30 and (ventas_total + rel["Ventas"]) > 0:
        tc = fg.wilson_lb(ventas_total + rel["Ventas"], leads_total + rel["Leads"])
        tc_fuente = (f"relanzamientos {rel['Lanzamientos']}x45d + actual "
                     f"({ventas_total + rel['Ventas']}/{leads_total + rel['Leads']})")
    elif leads_total >= 30 and ventas_total > 0:
        tc = fg.wilson_lb(ventas_total, leads_total)
        tc_fuente = "producto (Wilson LB)"
    elif tc_familia:
        tc = fg.wilson_lb(*tc_familia)
        tc_fuente = f"familia {familia} (Wilson LB, {tc_familia[0]}/{tc_familia[1]})"
    else:
        tc = 0.0
        tc_fuente = "sin muestra"

    # ---- estado actual del funnel ----
    funnel = {int(r["IdEstado"]): int(r["N"]) for r in db.query(SQL_FUNNEL_ESTADO, [prod["Id"]])}
    activos = sum(funnel.get(e, 0) for e in (1, 4, 5, 6))

    # ---- GP de leads (suma de los próximos 7 días) ----
    gp_leads = None
    prep = fg.prepare_xy(l_dates, l_counts, lookback_dias=args.lookback,
                         min_valid=args.min_valid_leads, hoy=hoy)
    if prep is not None:
        X, y, sc = prep
        model, _ = fg.init_and_train(X, y)
        gp_leads = fg.predict_one_week_ahead(model, sc, optimism_q=args.optimism)

    # ---- proyección de ventas al deadline (GP diario; ventas no filtran min_valid) ----
    prep_v = fg.prepare_xy(v_dates, v_counts, lookback_dias=args.lookback,
                           min_valid=None, hoy=hoy)
    if prep_v is not None:
        Xv, yv, scv = prep_v
        mv, _ = fg.init_and_train(Xv, yv)
        proj = fg.project_cumulative(mv, scv, dias_rest)
        proy = dict(mean=ventas_total + proj["mean"], p05=ventas_total + proj["p05"],
                    p95=ventas_total + proj["p95"], metodo="GP")
    else:
        # equivalente semanal de la mediana diaria reciente (últimos 14 días)
        mediana_sem = (statistics.median(l_counts[-14:]) * 7) if l_counts else 0.0
        proy = fg.project_fallback_wilson(ventas_total, leads_total, mediana_sem,
                                          sem_rest, tc_familia)

    # ---- break-even + decisión ----
    cac = cac_runtime(params)
    be = fg.compute_breakeven(ticket_usd, tc, args.cpl, args.docente, cac["blend"], params)
    decision = fg.decidir(be.n_be, proy["mean"], proy["p95"])
    leads_sem = fg.leads_semanales_necesarios(be.n_be, ventas_total, tc, sem_rest)

    # ---- reporte ----
    print(f"\n## Forecast — {prod['Nombre']} ({prod['Codigo'] or prod['Id']})\n")
    output([
        {"Campo": "Desarrollador", "Valor": prod["Desarrollador"] or "(sin asignar)"},
        {"Campo": "Deadline (inicio)", "Valor": str(deadline)},
        {"Campo": "Semanas restantes", "Valor": sem_rest},
        {"Campo": "Leads históricos", "Valor": leads_total},
        {"Campo": "Ventas actuales", "Valor": ventas_total},
        {"Campo": "Funnel activo", "Valor": f"{activos:,} (Reg {funnel.get(1, 0):,} / "
                                            f"Cal {funnel.get(4, 0):,} / Pot {funnel.get(5, 0):,} / "
                                            f"Prom {funnel.get(6, 0):,})"},
        {"Campo": "TC usada", "Valor": f"{fmt_pct(tc)} — {tc_fuente}"},
        {"Campo": "Ticket promedio venta", "Valor": f"USD {ticket_usd:,.2f} — {ticket_fuente} "
                                                    f"(precio al cliente)"},
    ])

    if gp_leads:
        print(f"\n### GP diario de leads — suma de los próximos 7 días "
              f"(P{int(args.optimism*100)} optimista)\n")
        output([{
            "Media": round(gp_leads["mean"], 1),
            "Pesimista": round(gp_leads["pessimistic"], 1),
            "CI95 inf": round(gp_leads["lower"], 1),
            "CI95 sup": round(gp_leads["upper"], 1),
            "P80": round(gp_leads["p80"], 1),
            "P90": round(gp_leads["p90"], 1),
            "P95": round(gp_leads["p95"], 1),
        }])
    else:
        print(f"\n(GP de leads no ajustado: menos de {fg.MIN_PUNTOS_GP} días válidos de leads)")

    print(f"\n### Proyección de ventas acumuladas al {deadline} — método {proy.get('metodo','GP')}\n")
    output([{
        "Pesimista (p05)": round(proy["p05"], 1),
        "Media": round(proy["mean"], 1),
        "Optimista (p95)": round(proy["p95"], 1),
        "N break-even": be.n_be if be.n_be is not None else "INVIABLE",
    }])

    print("\n### Break-even (PEN)\n")
    ticket_pen = ticket_usd * params.usd_pen
    output([
        {"Concepto": "Ticket promedio venta (precio al cliente)", "PEN": round(ticket_pen, 2)},
        {"Concepto": f"(-) Comisiones {fmt_pct(params.comision_pct, 0)} (no afecta al ticket)",
         "PEN": round(ticket_pen * params.comision_pct, 2)},
        {"Concepto": f"(-) Costos administrativos {fmt_pct(params.admin_pct, 0)}",
         "PEN": round(ticket_pen * params.admin_pct, 2)},
        {"Concepto": "(=) Ticket neto", "PEN": round(be.ticket_neto_pen, 2)},
        {"Concepto": f"CAC asesor blend (FT {cac['FT']['cac']:.0f} / PT {cac['PT']['cac']:.0f})",
         "PEN": round(be.cac_asesor_pen, 2)},
        {"Concepto": "CPL por venta (CPL / TC)", "PEN": round(be.cpl_por_venta_pen, 2)},
        {"Concepto": "Margen por venta", "PEN": round(be.margen_por_venta_pen, 2)},
        {"Concepto": "Costo docente (fijo)", "PEN": round(args.docente, 2)},
    ])

    print(f"\n### DECISIÓN: **{decision}**\n")
    if decision == "CANCELAR":
        if be.n_be is None:
            print("Motivo: margen por venta ≤ 0 — cada venta pierde plata; generar más leads solo agranda la pérdida.")
        else:
            print(f"Motivo: ni el escenario optimista (p95 = {proy['p95']:.1f}) alcanza el break-even (N_BE = {be.n_be}) antes del {deadline}.")
        print(f"Pérdida evitada estimada: {fmt_money(args.docente)} de docente + CPL de leads futuros.")
    elif leads_sem is not None:
        faltan = max(0, (be.n_be or 0) - ventas_total)
        print(f"Ventas faltantes para break-even: {faltan}. "
              f"Leads a solicitar: **{leads_sem}/semana** durante {sem_rest} semanas "
              f"(TC {fmt_pct(tc)}).")
        if decision == "RIESGO":
            print("RIESGO: solo el escenario optimista alcanza el break-even — vigilar semanalmente.")
    print(f"\nSupuestos: TC cambio {params.usd_pen}, comisiones {fmt_pct(params.comision_pct)}, "
          f"admin {fmt_pct(params.admin_pct)}, CAC ventana {VENTANA_CAC_DIAS} días. "
          f"La proyección asume flujo de leads 'business as usual'.")


if __name__ == "__main__":
    main()
