#!/usr/bin/env python3
"""
Portafolio por persona de desarrollo / encargado del curso (Producto.PersonalCreacion).

Muestra INGRESOS y ESTADO ACTUAL del portafolio de cada encargado (leads, matrículas,
TC, cobrado y comprometido). NO calcula rentabilidad/margen: la rentabilidad se analiza
por producto con producto_pnl.py / producto_compare.py. Aquí solo interesa cuánto captó
y cuánto ingresó cada portafolio.

La ancla temporal de las columnas de PLATA la elige --base:

  --base creacion (DEFAULT, cohorte): toda la plata pertenece a las oportunidades
     CREADAS en la ventana [--comp-desde,--comp-hasta), sin importar cuándo se
     pagó/matriculó. Cobrado = todos los pagos de esas oportunidades; comprometido =
     matrículas de esas oportunidades. TC = conversión real de la cohorte. Es
     consistente con el portafolio y LeadsVentana, que ya se definen por FechaCreacion.

  --base evento (ventana): cobrado por fecha de pago (desde --desde) y comprometido
     por fecha de matrícula dentro de la ventana. Mide caja que entró / ventas
     cerradas en el período aunque el lead sea anterior. TC = proxy.

Solo se incluyen productos con encargado válido: INNER JOIN a adm.Personal excluye
productos sin encargado (NULL) y los PersonalCreacion huérfanos (ids de prueba que
no existen en adm.Personal, p.ej. 165 y 218).

Uso:
  python scripts/portafolio_encargado.py
  python scripts/portafolio_encargado.py --desde 2026-01-01 --comp-desde 2026-04-01 --comp-hasta 2026-06-01
  python scripts/portafolio_encargado.py --fmt csv -o portafolio.csv
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cli, db, queries
from lib.calc import CostParams
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="Ingresos y estado de portafolio por encargado del curso")
    ap.add_argument("--base", choices=["creacion", "evento"], default="creacion",
                    help="Ancla temporal de las columnas de PLATA (cobrado/comprometido). "
                         "'creacion' (DEFAULT): base cohorte — todo se ancla a la fecha de creación "
                         "de la oportunidad. Cobrado = todos los pagos de oportunidades creadas en "
                         "[--comp-desde,--comp-hasta); comprometido = matrículas de esas mismas "
                         "oportunidades. TC = conversión real de cohorte. --desde se ignora. "
                         "'evento': base ventana — cobrado por fecha de pago (desde --desde) y "
                         "comprometido por fecha de matrícula en [--comp-desde,--comp-hasta).")
    ap.add_argument("--desde", default="2026-01-01",
                    help="Fecha desde para COBRADO (YYYY-MM-DD). Solo aplica con --base evento.")
    ap.add_argument("--comp-desde", default="2026-04-01",
                    help="Inicio de la ventana/cohorte (YYYY-MM-DD). Define el portafolio y, con "
                         "--base creacion, también el anclaje de toda la plata.")
    ap.add_argument("--comp-hasta", default="2026-06-01", help="Fin de la ventana/cohorte, exclusivo (YYYY-MM-DD)")
    ap.add_argument("--historico", action="store_true",
                    help="Incluir TODO el portafolio histórico del encargado. Por default solo se "
                         "cuentan productos con leads CREADOS en la ventana de comprometido.")
    ap.add_argument("--min-leads", type=int, default=20,
                    help="Mínimo de leads creados en la ventana para contar un producto como parte "
                         "del portafolio del período (default 20). Corta cohortes viejas que solo "
                         "captaron leads de goteo. Ignorado con --historico.")
    ap.add_argument("--usd-pen", type=float, help="Override tipo de cambio USD->PEN (solo aplica con --moneda pen)")
    cli.add_moneda(ap)
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    args = ap.parse_args()

    p = CostParams.from_env()
    if args.usd_pen is not None: p.usd_pen = args.usd_pen
    factor, suf = cli.factor_moneda(args.moneda, p.usd_pen)

    # 1. productos con encargado válido (excluye NULL y huérfanos)
    prods = db.query(queries.SQL_PRODUCTOS_ENCARGADO)
    # 2. matrículas por producto (para saber cuáles tuvieron venta)
    lm = db.query(queries.SQL_LEADS_MATRIC_POR_PRODUCTO)
    matric = {r["P"]: r["Matric"] for r in lm}
    # 3+4. cobrado y comprometido — el ancla temporal depende de --base
    if args.base == "creacion":
        # Cohorte: toda la plata pertenece a las oportunidades CREADAS en la ventana,
        # sin importar cuándo se pagó/matriculó. Consistente con el portafolio y LeadsVentana.
        cb = db.query(queries.SQL_COBRADO_COHORTE_POR_PRODUCTO, [args.comp_desde, args.comp_hasta])
        win = db.query(queries.SQL_COMPROMETIDO_COHORTE_POR_PRODUCTO, [args.comp_desde, args.comp_hasta])
    else:
        # Evento/ventana: cobrado por fecha de pago (desde --desde), comprometido por
        # fecha de matrícula dentro de la ventana. --desde solo aplica en este modo.
        cb = db.query(queries.SQL_COBRADO_DESDE_POR_PRODUCTO, [args.desde])
        win = db.query(queries.SQL_COMPROMETIDO_VENTANA_POR_PRODUCTO, [args.comp_desde, args.comp_hasta])
    cobrado = {r["P"]: float(r["CobradoUSD"] or 0) for r in cb}
    matric_win = {r["P"]: r["MatricVentana"] for r in win}
    comp_win = {r["P"]: float(r["CompVentanaUSD"] or 0) for r in win}
    # 4b. leads CREADOS en la ventana (define la cartera activa junto con las ventas)
    lw = db.query(queries.SQL_LEADS_VENTANA_POR_PRODUCTO, [args.comp_desde, args.comp_hasta])
    leads_win = {r["P"]: r["LeadsVentana"] for r in lw}

    # Acumular por encargado
    agg = defaultdict(lambda: {"Encargado": "", "ProdConVenta": 0, "ProdSinVenta": 0,
                               "Productos": 0, "LeadsVentana": 0, "MatricVentana": 0, "TC": 0.0,
                               "IngCobrado": 0.0, "IngCompVentana": 0.0})
    for pr in prods:
        pid = pr["Id"]
        lw_in = leads_win.get(pid, 0)
        # cartera del período = productos que CAPTARON >= min_leads leads creados en
        # la ventana. El umbral corta cohortes viejas con goteo de 1-7 leads sueltos.
        # --historico incluye todo el portafolio histórico del encargado.
        if not args.historico and lw_in < args.min_leads:
            continue

        # Ingresos en la moneda elegida (cobrado de la cohorte / comprometido de la ventana)
        ing1 = cobrado.get(pid, 0.0) * factor
        mw = matric_win.get(pid, 0)
        ing2 = comp_win.get(pid, 0.0) * factor

        a = agg[pr["Encargado"]]
        a["Encargado"] = pr["EncargadoNombre"] or f"id={pr['Encargado']}"
        a["Productos"] += 1
        a["LeadsVentana"] += lw_in
        a["MatricVentana"] += mw
        a["IngCobrado"] += ing1
        a["IngCompVentana"] += ing2
        if mw > 0:
            a["ProdConVenta"] += 1
        else:
            a["ProdSinVenta"] += 1

    rows = [v for v in agg.values() if v["IngCobrado"] != 0 or v["IngCompVentana"] != 0]
    rows.sort(key=lambda x: x["IngCobrado"], reverse=True)
    total_cobrado = sum(r["IngCobrado"] for r in rows) or 1.0
    n_personas = len(rows)
    for r in rows:
        # TC = matriculados / leads creados en la ventana. Con --base creacion numerador y
        # denominador son la MISMA cohorte (conversión real); con --base evento el numerador
        # (matrículas por fecha de evento) puede venir de leads creados antes → proxy.
        r["TC"] = round(100.0 * r["MatricVentana"] / r["LeadsVentana"], 2) if r["LeadsVentana"] else 0.0
        # % del ingreso cobrado del encargado sobre el total del portafolio.
        r["%Cobrado"] = round(100.0 * r["IngCobrado"] / total_cobrado, 2)
        for k in ("IngCobrado", "IngCompVentana"):
            r[k] = round(r[k], 2)

    # Fila TOTAL: suma de las columnas cuantitativas del portafolio.
    if rows:
        total = {"Encargado": "TOTAL"}
        for k in ("ProdConVenta", "ProdSinVenta", "Productos", "LeadsVentana",
                  "MatricVentana", "IngCobrado", "IngCompVentana"):
            total[k] = round(sum(r[k] for r in rows), 2)
        total["TC"] = round(100.0 * total["MatricVentana"] / total["LeadsVentana"], 2) if total["LeadsVentana"] else 0.0
        total["%Cobrado"] = 100.0
        rows.append(total)

    cartera = ("histórico completo del portafolio"
               if args.historico
               else f"productos con >={args.min_leads} leads CREADOS en "
                    f"{args.comp_desde}..{args.comp_hasta} (cartera lanzada en el período)")
    if args.base == "creacion":
        base_txt = (f">>> BASE = COHORTE (fecha de creación de la oportunidad): toda la plata se ancla a "
                    f"Oportunidad.FechaCreacion en {args.comp_desde}..{args.comp_hasta} (exclusivo). "
                    f"Cobrado = todos los pagos de esas oportunidades; comprometido = matrículas de esas "
                    f"oportunidades. TC = conversión real de la cohorte. (--desde ignorado en este modo.)\n"
                    f">>> También se puede calcular por VENTANA/evento con --base evento "
                    f"(cobrado por fecha de pago, comprometido por fecha de matrícula).\n")
    else:
        base_txt = (f">>> BASE = EVENTO/VENTANA: cobrado por fecha de pago desde {args.desde}; "
                    f"comprometido/matrículas por fecha de matrícula en {args.comp_desde}..{args.comp_hasta} "
                    f"(exclusivo). TC = proxy (numerador y denominador no son la misma cohorte).\n"
                    f">>> También se puede calcular por COHORTE con --base creacion "
                    f"(default; toda la plata anclada a la fecha de creación de la oportunidad).\n")
    print(
        f">>> Encargados con encargado válido (excluye NULL y huérfanos) · {n_personas} personas\n"
        f">>> Productos = {cartera}\n"
        f"{base_txt}"
        f">>> Ingresos en {suf}{f' (USD/PEN={p.usd_pen})' if args.moneda == 'pen' else ''}. "
        f"Este reporte NO calcula rentabilidad/margen: "
        f"para eso usa producto_pnl.py / producto_compare.py por producto.\n",
        file=sys.stderr,
    )
    output(rows, fmt=args.fmt, out_path=args.output,
           headers=["Encargado", "ProdConVenta", "ProdSinVenta", "Productos",
                    "LeadsVentana", "MatricVentana", "TC",
                    "IngCobrado", "%Cobrado", "IngCompVentana"])


if __name__ == "__main__":
    main()
