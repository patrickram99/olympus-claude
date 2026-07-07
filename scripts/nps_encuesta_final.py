#!/usr/bin/env python3
"""
NPS (Net Promoter Score) a partir de la ENCUESTA FINAL de cada módulo.

Fuente: adm.EncuestaFinalRespuestas.RecomendacionEscala (0-10, "¿qué tan probable
es que recomiendes...?"). Clasificación estándar NPS:
  - Promotores  = 9-10
  - Pasivos     = 7-8
  - Detractores = 0-6
  NPS = %Promotores - %Detractores   (entero entre -100 y +100)

Atribución al DESARROLLADOR (persona de desarrollo / encargado del curso):
  EncuestaFinalRespuestas.IdModulo
    -> adm.EstructuraCurricularModulo.IdModulo -> .IdEstructuraCurricular
    -> adm.EstructuraCurricular.IdProducto
    -> adm.Producto.PersonalCreacion  (= desarrollador)
    -> adm.Personal (nombre)

OJO — many-to-many módulo↔producto: un mismo módulo puede reutilizarse en varios
productos (cohortes May/Jun, variantes), lo que infla las respuestas si se hace el
JOIN directo. PERO a nivel desarrollador la atribución es única: 35 de 36 módulos
encuestados mapean a exactamente 1 desarrollador (los productos que comparten un
módulo comparten dueño). Por eso deduplicamos módulo->desarrollador con MIN() ANTES
de tocar las respuestas: cada respuesta se cuenta UNA sola vez. Los módulos cuyo
producto tiene PersonalCreacion NULL o huérfano (no existe en adm.Personal) caen a
la etiqueta "(sin desarrollador)".

Uso:
  python scripts/nps_encuesta_final.py                       # NPS por desarrollador
  python scripts/nps_encuesta_final.py --nivel modulo        # NPS por módulo (+ su desarrollador)
  python scripts/nps_encuesta_final.py --nivel detalle       # módulos agrupados bajo cada desarrollador
  python scripts/nps_encuesta_final.py --desde 2026-06-01    # sólo respuestas desde una fecha
  python scripts/nps_encuesta_final.py --min-resp 5          # oculta muestras < 5 respuestas
  python scripts/nps_encuesta_final.py --timeline --desde 2026-06-01 --hasta 2026-06-30  # timeline semanal de junio (todos)
  python scripts/nps_encuesta_final.py --nivel modulo --fmt csv -o nps.csv

Caveat: NPS con n chico es ruidoso (una sola respuesta mueve el número decenas de
puntos). El script marca con '*' toda fila con menos de --min-resp respuestas
(default 5) en vez de ocultarla; pasa --ocultar-chicas para excluirlas.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db
from lib.format import output

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")

# Mapa único módulo -> desarrollador (dedup con MIN para no inflar por many-to-many).
# LEFT JOIN para conservar módulos sin producto/dueño (caen a IdDev NULL).
_MAPA_MOD_DEV = """
    SELECT ecm.IdModulo, MIN(pr.PersonalCreacion) AS IdDev
    FROM adm.EstructuraCurricularModulo ecm
    JOIN adm.EstructuraCurricular ec ON ec.Id = ecm.IdEstructuraCurricular AND ec.Estado = 1
    JOIN adm.Producto pr             ON pr.Id = ec.IdProducto AND pr.Estado = 1
    WHERE ecm.Estado = 1
    GROUP BY ecm.IdModulo
"""

# Expresiones NPS reutilizadas
_PROM = "SUM(CASE WHEN e.RecomendacionEscala >= 9 THEN 1 ELSE 0 END)"
_PAS  = "SUM(CASE WHEN e.RecomendacionEscala BETWEEN 7 AND 8 THEN 1 ELSE 0 END)"
_DET  = "SUM(CASE WHEN e.RecomendacionEscala <= 6 THEN 1 ELSE 0 END)"


def _valid_date(s: str | None) -> str | None:
    if s and not _ISO.fullmatch(s):
        print(f"ERROR: fecha debe ser YYYY-MM-DD, recibido: {s!r}", file=sys.stderr)
        sys.exit(2)
    return s


def _where(desde: str | None, hasta: str | None) -> tuple[str, list]:
    conds = ["e.Estado = 1"]
    params: list = []
    if desde:
        conds.append("e.FechaCreacion >= ?")
        params.append(desde)
    if hasta:
        conds.append("e.FechaCreacion < DATEADD(DAY, 1, CAST(? AS DATE))")
        params.append(hasta)
    return " AND ".join(conds), params


def _nps(prom: int, det: int, n: int) -> float:
    return round(100.0 * prom / n - 100.0 * det / n, 1) if n else 0.0


def _fetch(select_extra: str, join_extra: str, group_by: str, where: str, params: list) -> list[dict]:
    sql = f"""
    SELECT {select_extra}
           COUNT(*) AS Resp,
           {_PROM} AS Prom,
           {_PAS}  AS Pas,
           {_DET}  AS Det
    FROM adm.EncuestaFinalRespuestas e
    JOIN ({_MAPA_MOD_DEV}) mm ON mm.IdModulo = e.IdModulo
    LEFT JOIN adm.Personal per ON per.Id = mm.IdDev AND per.Estado = 1
    {join_extra}
    WHERE {where}
    GROUP BY {group_by}
    """
    return db.query(sql, params)


def _dev_name(row: dict) -> str:
    n = (row.get("Nombres") or "").strip()
    a = (row.get("Apellidos") or "").strip()
    full = f"{n} {a}".strip()
    return full or "(sin desarrollador)"


def main():
    ap = argparse.ArgumentParser(description="NPS de la encuesta final por desarrollador / módulo")
    ap.add_argument("--nivel", choices=["desarrollador", "modulo", "detalle"], default="desarrollador",
                    help="desarrollador (default): 1 fila por dev · modulo: 1 fila por módulo · "
                         "detalle: módulos agrupados bajo cada dev")
    ap.add_argument("--timeline", choices=["dia", "semana", "mes"], nargs="?", const="semana",
                    help="Evolución del NPS en el tiempo (de TODAS las respuestas del filtro, agregadas). "
                         "Sin valor = semana. Ignora --nivel. Combínalo con --desde/--hasta (p.ej. junio: "
                         "--timeline --desde 2026-06-01 --hasta 2026-06-30).")
    ap.add_argument("--desde", help="Respuestas con FechaCreacion >= YYYY-MM-DD")
    ap.add_argument("--hasta", help="Respuestas con FechaCreacion <= YYYY-MM-DD (inclusive)")
    ap.add_argument("--min-resp", type=int, default=5,
                    help="Umbral de muestra chica: filas con menos respuestas se marcan con '*' (default 5)")
    ap.add_argument("--ocultar-chicas", action="store_true",
                    help="Excluye (en vez de marcar) las filas con menos de --min-resp respuestas")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    desde = _valid_date(args.desde)
    hasta = _valid_date(args.hasta)
    where, params = _where(desde, hasta)

    rows: list[dict] = []

    # --- Modo timeline: NPS agregado de TODAS las respuestas, por período ---
    if args.timeline:
        period_sql = {
            "dia": "CAST(e.FechaCreacion AS DATE)",
            "semana": "CAST(DATEADD(WEEK, DATEDIFF(WEEK, 0, e.FechaCreacion), 0) AS DATE)",
            "mes": "DATEFROMPARTS(YEAR(e.FechaCreacion), MONTH(e.FechaCreacion), 1)",
        }[args.timeline]
        etiqueta = {"dia": "Día", "semana": "Semana (lun)", "mes": "Mes"}[args.timeline]
        sql = (
            f"SELECT {period_sql} AS Periodo, COUNT(*) AS Resp, {_PROM} AS Prom, "
            f"{_PAS} AS Pas, {_DET} AS Det "
            f"FROM adm.EncuestaFinalRespuestas e WHERE {where} "
            f"GROUP BY {period_sql} ORDER BY 1"
        )
        for r in db.query(sql, params):
            n, prom, pas, det = int(r["Resp"]), int(r["Prom"]), int(r["Pas"]), int(r["Det"])
            rows.append({
                etiqueta: str(r["Periodo"])[:10],
                "Resp": n, "Prom": prom, "Pas": pas, "Det": det,
                "NPS": (f"{_nps(prom, det, n)}*" if n < args.min_resp and not args.ocultar_chicas
                        else _nps(prom, det, n)),
                "_chica": n < args.min_resp,
            })
        if args.ocultar_chicas:
            rows = [r for r in rows if not r["_chica"]]
        for r in rows:
            r.pop("_chica", None)
        # fila TOTAL del período
        if rows:
            tn = sum(r["Resp"] for r in rows)
            tprom = sum(r["Prom"] for r in rows)
            tpas = sum(r["Pas"] for r in rows)
            tdet = sum(r["Det"] for r in rows)
            rows.append({etiqueta: "TOTAL", "Resp": tn, "Prom": tprom, "Pas": tpas,
                         "Det": tdet, "NPS": _nps(tprom, tdet, tn)})
        ventana = f"{desde or 'inicio'} → {hasta or 'hoy'}"
        print(f"\n>>> NPS Encuesta Final · timeline={args.timeline} · {ventana} · "
              f"'*' = período < {args.min_resp} resp\n", file=sys.stderr)
        output(rows, fmt=args.fmt, out_path=args.output)
        return

    if args.nivel == "desarrollador":
        data = _fetch(
            "per.Id AS DevId, per.Nombres, per.Apellidos,",
            "", "per.Id, per.Nombres, per.Apellidos", where, params,
        )
        for r in data:
            n, prom, pas, det = int(r["Resp"]), int(r["Prom"]), int(r["Pas"]), int(r["Det"])
            rows.append({
                "Desarrollador": _dev_name(r),
                "Resp": n, "Prom": prom, "Pas": pas, "Det": det,
                "NPS": _nps(prom, det, n),
                "chica": n < args.min_resp,
            })
        rows.sort(key=lambda x: (-x["NPS"], -x["Resp"]))

    else:  # modulo o detalle: siempre partimos del detalle por módulo
        data = _fetch(
            "per.Id AS DevId, per.Nombres, per.Apellidos, m.Id AS ModId, m.Nombre AS Modulo, m.Codigo AS CodModulo,",
            "JOIN adm.Modulo m ON m.Id = e.IdModulo",
            "per.Id, per.Nombres, per.Apellidos, m.Id, m.Nombre, m.Codigo", where, params,
        )
        detalle = []
        for r in data:
            n, prom, pas, det = int(r["Resp"]), int(r["Prom"]), int(r["Pas"]), int(r["Det"])
            detalle.append({
                "Desarrollador": _dev_name(r),
                "Modulo": (r["Modulo"] or "").strip(),
                "CodModulo": r["CodModulo"],
                "Resp": n, "Prom": prom, "Pas": pas, "Det": det,
                "NPS": _nps(prom, det, n),
                "chica": n < args.min_resp,
            })

        if args.nivel == "modulo":
            detalle.sort(key=lambda x: (-x["NPS"], -x["Resp"]))
            rows = detalle
        else:  # detalle: subtotal por dev + sus módulos
            devs: dict[str, list[dict]] = {}
            for d in detalle:
                devs.setdefault(d["Desarrollador"], []).append(d)
            # ordena devs por su NPS agregado desc
            def dev_nps(mods):
                n = sum(m["Resp"] for m in mods)
                prom = sum(m["Prom"] for m in mods)
                det = sum(m["Det"] for m in mods)
                return _nps(prom, det, n), n, prom, det
            for dev in sorted(devs, key=lambda k: (-dev_nps(devs[k])[0], -dev_nps(devs[k])[1])):
                mods = devs[dev]
                nps, n, prom, det = dev_nps(mods)
                pas = sum(m["Pas"] for m in mods)
                rows.append({
                    "Desarrollador / Módulo": dev.upper(),
                    "Cod": "", "Resp": n, "Prom": prom, "Pas": pas, "Det": det,
                    "NPS": nps, "chica": n < args.min_resp,
                })
                for m in sorted(mods, key=lambda x: (-x["NPS"], -x["Resp"])):
                    rows.append({
                        "Desarrollador / Módulo": "  " + m["Modulo"],
                        "Cod": m["CodModulo"], "Resp": m["Resp"], "Prom": m["Prom"],
                        "Pas": m["Pas"], "Det": m["Det"], "NPS": m["NPS"],
                        "chica": m["chica"],
                    })

    # marca '*' muestras chicas o filtra
    if args.ocultar_chicas:
        rows = [r for r in rows if not r.get("chica")]
    for r in rows:
        if r.pop("chica", False):
            r["NPS"] = f"{r['NPS']}*"

    # fila TOTAL global (siempre sobre respuestas activas del filtro)
    tot = db.query(
        f"SELECT COUNT(*) AS Resp, {_PROM} AS Prom, {_PAS} AS Pas, {_DET} AS Det "
        f"FROM adm.EncuestaFinalRespuestas e WHERE {where.replace('per.', 'e.')}",
        params,
    )[0]
    tn, tprom, tpas, tdet = int(tot["Resp"]), int(tot["Prom"]), int(tot["Pas"]), int(tot["Det"])
    total_row = {k: "" for k in rows[0]} if rows else {}
    first_key = list(rows[0].keys())[0] if rows else "Desarrollador"
    total_row[first_key] = "TOTAL (todas las respuestas)"
    total_row.update({"Resp": tn, "Prom": tprom, "Pas": tpas, "Det": tdet, "NPS": _nps(tprom, tdet, tn)})
    if "Cod" in total_row:
        total_row["Cod"] = ""
    rows.append(total_row)

    ventana = f"{desde or 'inicio'} → {hasta or 'hoy'}"
    print(f"\n>>> NPS Encuesta Final · nivel={args.nivel} · {ventana} · "
          f"'*' = muestra < {args.min_resp} resp\n", file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
