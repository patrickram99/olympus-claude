#!/usr/bin/env python3
"""
Cursos en estado "En venta" (adm.Producto.EstadoProductoTipoId = 20): foto del
funnel actual (stock por etapa vigente), inscritos, promesas, TC e ingresos
comprometidos/cobrados por curso.

A diferencia de programas_top_ventas.py (que rankea CUALQUIER curso con ventas en
una ventana), esto lista SOLO los productos cuyo estado de catálogo es "En venta"
— la cartera que hoy se está comercializando.

- Funnel = último HistorialEstado por oportunidad (foto del stock, no flujo).
- Inscritos (Ins) = oportunidades cuyo estado vigente es Matriculado (3).
- Perdidos = Perdido (7) + No calificado (2).
- Ingresos = cohorte all-time del curso: comprometido = plan de las matriculadas;
  cobrado = pagos reales. Moneda USD por defecto (--moneda pen para soles).

Uso:
  python scripts/cursos_en_venta.py                          # tabla en pantalla
  python scripts/cursos_en_venta.py --desarrollador "Ramírez"  # filtra por dev
  python scripts/cursos_en_venta.py --desarrollador 81         # filtra por Id de dev
  python scripts/cursos_en_venta.py --fmt xlsx -o "C:/Users/patra/Downloads/cursos.xlsx"
  python scripts/cursos_en_venta.py --excluir ""             # NO excluir nada
  python scripts/cursos_en_venta.py --excluir "mundialer|titulab|generico"

Por default excluye las campañas "Mundialero" (regex `mundialer`), que no son
cursos reales sino paraguas de captación.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cli, db
from lib.calc import CostParams
from lib.format import output

EN_VENTA = 20  # adm.Tipo.Id (categoria EstadoProducto) = "En venta"


def _fold(s: str) -> str:
    """Minúsculas sin acentos, para matching robusto de nombres (la DB guarda
    'Ramirez' sin tilde, el usuario escribe 'Ramírez')."""
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower())
                   if not unicodedata.combining(c))

# Columnas del Excel, en el orden exacto pedido por el usuario.
# TC = Ins/Leads. TCProc = Ins/(Leads-Reg) = conversión sobre leads YA procesados
# (todo menos Registrado, que aún no se ha llamado).
XLSX_COLS = ["Codigo", "Curso", "Leads", "Reg", "Cal", "Pot", "Prom",
             "Ins", "TC", "TCProc", "Perdidos", "Comprometido", "Cobrado", "%Cob"]
# Columnas de la vista rica (tabla/csv): agrega Desarrollador. El Id interno
# no se muestra — el identificador de negocio es el Codigo.
FULL_COLS = ["Codigo", "Curso", "Desarrollador", "Leads", "Reg", "Cal",
             "Pot", "Prom", "Ins", "TC", "TCProc", "Perdidos", "Comprometido", "Cobrado", "%Cob"]

SQL_PRODUCTOS = """
SELECT pr.Id,
  ISNULL(pr.CodigoLanzamiento, '') AS Codigo,
  pr.Nombre,
  pr.PersonalCreacion AS DevId,
  LTRIM(RTRIM(ISNULL(per.Nombres, '') + ' ' + ISNULL(per.Apellidos, ''))) AS DevNombre
FROM adm.Producto pr
LEFT JOIN adm.Personal per ON per.Id = pr.PersonalCreacion AND per.Estado = 1
WHERE pr.Estado = 1 AND pr.EstadoProductoTipoId = ?
"""

SQL_FUNNEL = """
SELECT op.IdProducto AS P, cur.IdEstado, COUNT(*) AS N
FROM (
  SELECT he.IdOportunidad, he.IdEstado,
    ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion DESC, he.Id DESC) AS rn
  FROM adm.HistorialEstado he WHERE he.Estado = 1
) cur
INNER JOIN adm.Oportunidad op ON op.Id = cur.IdOportunidad AND op.Estado = 1
INNER JOIN adm.Producto pr ON pr.Id = op.IdProducto AND pr.Estado = 1 AND pr.EstadoProductoTipoId = ?
WHERE cur.rn = 1
GROUP BY op.IdProducto, cur.IdEstado
"""

SQL_INGRESOS = """
SELECT q.IdProducto AS P,
  SUM(cp.Total) AS Compr,
  ISNULL(SUM(pg.Monto), 0) AS Cobr
FROM (
  SELECT DISTINCT op.IdProducto, op.Id AS IdOportunidad
  FROM adm.HistorialEstado h
  INNER JOIN adm.Oportunidad op ON op.Id = h.IdOportunidad AND op.Estado = 1
  INNER JOIN adm.Producto pr ON pr.Id = op.IdProducto AND pr.Estado = 1 AND pr.EstadoProductoTipoId = ?
  WHERE h.Estado = 1 AND h.IdEstado = 3
) q
INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = q.IdOportunidad AND cp.Estado = 1
LEFT JOIN adm.CobranzaPago pg ON pg.IdCobranzaPlan = cp.Id AND pg.Estado = 1
GROUP BY q.IdProducto
"""


def build_rows(factor: float, excluir: str | None, desarrollador: str | None):
    """factor: multiplicador sobre los montos USD de la BD (1.0=USD, usd_pen=PEN)."""
    prods = db.query(SQL_PRODUCTOS, [EN_VENTA])
    funnel = db.query(SQL_FUNNEL, [EN_VENTA])
    ingresos = db.query(SQL_INGRESOS, [EN_VENTA])

    fmap: dict[int, dict[int, int]] = {}
    for r in funnel:
        fmap.setdefault(int(r["P"]), {})[int(r["IdEstado"])] = int(r["N"])
    rmap = {int(r["P"]): (float(r["Compr"] or 0), float(r["Cobr"] or 0)) for r in ingresos}

    rex = re.compile(excluir, re.IGNORECASE) if excluir else None
    dev_num = desarrollador.isdigit() if desarrollador else False
    dev_txt = _fold(desarrollador) if (desarrollador and not dev_num) else None

    rows = []
    for p in prods:
        pid = int(p["Id"])
        codigo = (p["Codigo"] or "").strip()
        curso = (p["Nombre"] or "").strip()
        dev = (p["DevNombre"] or "").strip()
        dev_id = p["DevId"]

        if rex and rex.search(f"{codigo} {curso}"):
            continue
        if dev_num and str(dev_id) != desarrollador:
            continue
        if dev_txt and dev_txt not in _fold(dev):
            continue

        f = fmap.get(pid, {})
        reg, cal, pot, prom = f.get(1, 0), f.get(4, 0), f.get(5, 0), f.get(6, 0)
        ins, perd, nocal = f.get(3, 0), f.get(7, 0), f.get(2, 0)
        total = reg + cal + pot + prom + ins + perd + nocal
        perdidos = perd + nocal
        procesados = total - reg  # leads ya llamados (todo menos Registrado)
        compr, cobr = rmap.get(pid, (0.0, 0.0))
        rows.append({
            "Codigo": codigo or f"id:{pid}",
            "Curso": curso,
            "Desarrollador": dev or "(sin encargado)",
            "Leads": total,
            "Reg": reg, "Cal": cal, "Pot": pot, "Prom": prom,
            "Ins": ins,
            "TC": round(ins / total * 100, 2) if total else 0.0,
            "TCProc": round(ins / procesados * 100, 2) if procesados else 0.0,
            "Perdidos": perdidos,
            "Comprometido": round(compr * factor, 2),
            "Cobrado": round(cobr * factor, 2),
            "%Cob": round(cobr / compr * 100, 1) if compr else 0.0,
        })

    rows.sort(key=lambda r: (-r["Ins"], -r["Leads"]))
    return rows


def write_xlsx(rows: list[dict], out_path: str):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Cursos en venta"

    head_fill = PatternFill("solid", fgColor="1F4E78")
    head_font = Font(bold=True, color="FFFFFF")
    for c, name in enumerate(XLSX_COLS, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.fill = head_fill
        cell.font = head_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    money_cols = {XLSX_COLS.index("Comprometido") + 1, XLSX_COLS.index("Cobrado") + 1}
    tc_cols = {XLSX_COLS.index("TC") + 1, XLSX_COLS.index("TCProc") + 1,
               XLSX_COLS.index("%Cob") + 1}
    for r, row in enumerate(rows, 2):
        for c, name in enumerate(XLSX_COLS, 1):
            cell = ws.cell(row=r, column=c, value=row[name])
            if c in money_cols:
                cell.number_format = '#,##0'
            elif c in tc_cols:
                cell.number_format = '0.00'

    # Anchos y estética
    widths = {"Codigo": 30, "Curso": 46, "Comprometido": 14, "Cobrado": 13}
    for c, name in enumerate(XLSX_COLS, 1):
        ws.column_dimensions[get_column_letter(c)].width = widths.get(name, 8)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(XLSX_COLS))}{len(rows) + 1}"

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    print(f"wrote {len(rows)} cursos -> {out_path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description='Cursos en estado "En venta": funnel, TC e ingresos.')
    ap.add_argument("--desarrollador", help="Filtra por encargado del curso: Id numérico o texto del nombre (substring).")
    ap.add_argument("--excluir", default="mundialer",
                    help='Regex (case-insensitive) para excluir por código+nombre. Default "mundialer". Usa "" para no excluir.')
    ap.add_argument("--usd-pen", type=float, help="Tipo de cambio USD->PEN (default: config.toml). Solo aplica con --moneda pen.")
    cli.add_moneda(ap)
    ap.add_argument("--fmt", choices=["table", "csv", "json", "xlsx"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    usd_pen = args.usd_pen if args.usd_pen is not None else CostParams.from_env().usd_pen
    factor, suf = cli.factor_moneda(args.moneda, usd_pen)
    rows = build_rows(factor, args.excluir or None, args.desarrollador)

    scope = f" · dev~'{args.desarrollador}'" if args.desarrollador else ""
    excl = f" · excluye /{args.excluir}/" if args.excluir else ""
    tot_leads = sum(r["Leads"] for r in rows)
    tot_ins = sum(r["Ins"] for r in rows)
    tot_compr = sum(r["Comprometido"] for r in rows)
    tot_cobr = sum(r["Cobrado"] for r in rows)
    cambio = f"  ·  USD/PEN={usd_pen}" if args.moneda == "pen" else ""
    print(f"\n>>> CURSOS EN VENTA (EstadoProducto=20){scope}{excl}  ·  moneda={suf}{cambio}", file=sys.stderr)
    print(f">>> {len(rows)} cursos · Leads {tot_leads:,} · Inscritos {tot_ins:,} · "
          f"TC {tot_ins / tot_leads * 100:.2f}% · Comprometido {tot_compr:,.0f} {suf} · "
          f"Cobrado {tot_cobr:,.0f} {suf} ({tot_cobr / tot_compr * 100:.0f}%)\n" if tot_leads and tot_compr
          else f">>> {len(rows)} cursos · Leads {tot_leads:,} · Inscritos {tot_ins:,}\n", file=sys.stderr)

    if args.fmt == "xlsx":
        if not args.output:
            ap.error("--fmt xlsx requiere -o con la ruta del archivo .xlsx")
        write_xlsx(rows, args.output)
    else:
        output(rows, fmt=args.fmt, out_path=args.output, headers=FULL_COLS)


if __name__ == "__main__":
    main()
