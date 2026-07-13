#!/usr/bin/env python3
"""
Pagos a docentes del mes: módulos cuya ÚLTIMA sesión de clase cae dentro del mes
pedido, con el docente (nombre completo desde adm.Docente → adm.Persona), los
cursos padre a los que pertenece el módulo, las horas a pagar y las fechas de
dictado. La columna Monto (USD) sale VACÍA a propósito — la completa el usuario.

Lógica:
  1. Módulo "finaliza este mes" = MAX(SesionHorario.Fecha) de sus sesiones de
     clase (excluye la sesión de presentación) cae en [mes, mes+1).
  2. Cursos padre vía EstructuraCurricularModulo → EstructuraCurricular →
     Producto; --desarrollador filtra por el encargado del curso
     (Producto.PersonalCreacion) y muestra solo los cursos de ese dev.
  3. Horas = horas en vivo reales (suma de HoraFin-HoraInicio de sesiones
     síncronas, sin la presentación) + --async-horas (default 2, la sesión
     asincrónica estándar). Si las sesiones están registradas con duración
     cero (bug de carga conocido), estima 2h por sesión y marca con '*'.

Uso:
  python scripts/pagos_docentes.py                              # mes actual, todos
  python scripts/pagos_docentes.py --desarrollador "Patrick"    # portafolio de un dev
  python scripts/pagos_docentes.py --mes 2026-06 --fmt fichas   # formato de fichas
  python scripts/pagos_docentes.py --fmt csv -o pagos.csv
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db
from lib.format import output

HORAS_SESION_ESTIMADA = 2  # h por sesión cuando la duración registrada es 0 (bug de carga)

COLS = ["Docente", "Cursos", "CodigoModulo", "Modulo", "Horas",
        "FechaInicio", "FechaFin", "MontoUSD"]

# Módulos activos cuya última sesión de clase (sin la presentación) cae en el mes.
# La sesión de presentación es un evento de marketing previo al dictado: no cuenta
# ni para horas ni para fechas.
SQL_MODULOS = """
SELECT m.Id, m.Codigo, m.Nombre,
  LTRIM(RTRIM(ISNULL(pe.Nombres, '') + ' ' + ISNULL(pe.Apellidos, ''))) AS Docente,
  agg.HorasVivo, agg.SesionesVivo, agg.FechaInicio, agg.FechaFin
FROM adm.Modulo m
LEFT JOIN adm.Docente d ON d.Id = m.IdDocente AND d.Estado = 1
LEFT JOIN adm.Persona pe ON pe.Id = d.IdPersona
INNER JOIN (
  SELECT s.IdModulo,
    SUM(CASE WHEN sh.EsAsincronica = 0 AND s.Nombre NOT LIKE '%Presentaci%'
             THEN DATEDIFF(MINUTE, sh.HoraInicio, sh.HoraFin) ELSE 0 END) / 60.0 AS HorasVivo,
    COUNT(CASE WHEN sh.EsAsincronica = 0 AND s.Nombre NOT LIKE '%Presentaci%'
               THEN 1 END) AS SesionesVivo,
    MIN(CASE WHEN s.Nombre NOT LIKE '%Presentaci%' THEN sh.Fecha END) AS FechaInicio,
    MAX(CASE WHEN s.Nombre NOT LIKE '%Presentaci%' THEN sh.Fecha END) AS FechaFin
  FROM adm.Sesion s
  INNER JOIN adm.SesionHorario sh ON sh.IdSesion = s.Id AND sh.Estado = 1
  WHERE s.Estado = 1
  GROUP BY s.IdModulo
) agg ON agg.IdModulo = m.Id
WHERE m.Estado = 1 AND agg.FechaFin >= ? AND agg.FechaFin < ?
"""

# Cursos padre de cada módulo con su encargado (Producto.PersonalCreacion).
# LEFT JOIN a Personal: sin filtro de dev se listan también cursos sin encargado
# válido; con --desarrollador solo matchean los que tienen dev real.
SQL_CURSOS = """
SELECT ecm.IdModulo,
  ISNULL(p.CodigoLanzamiento, '') AS Codigo,
  p.Id AS ProductoId,
  p.PersonalCreacion AS DevId,
  LTRIM(RTRIM(ISNULL(per.Nombres, '') + ' ' + ISNULL(per.Apellidos, ''))) AS DevNombre
FROM adm.EstructuraCurricularModulo ecm
INNER JOIN adm.EstructuraCurricular ec ON ec.Id = ecm.IdEstructuraCurricular AND ec.Estado = 1
INNER JOIN adm.Producto p ON p.Id = ec.IdProducto AND p.Estado = 1
LEFT JOIN adm.Personal per ON per.Id = p.PersonalCreacion AND per.Estado = 1
WHERE ecm.Estado = 1
"""


def _fold(s: str) -> str:
    """Minúsculas sin acentos, para matching robusto de nombres."""
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower())
                   if not unicodedata.combining(c))


def mes_type(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise argparse.ArgumentTypeError(f"debe ser YYYY-MM, recibido {value!r}")
    y, m = int(value[:4]), int(value[5:7])
    if not 1 <= m <= 12:
        raise argparse.ArgumentTypeError(f"mes inexistente: {value!r}")
    return value


def rango_mes(mes: str) -> tuple[str, str]:
    """[primer día del mes, primer día del mes siguiente)."""
    y, m = int(mes[:4]), int(mes[5:7])
    sig = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return f"{mes}-01", sig.isoformat()


def build_rows(mes: str, async_horas: float, desarrollador: str | None):
    desde, hasta = rango_mes(mes)
    modulos = db.query(SQL_MODULOS, [desde, hasta])
    cursos = db.query(SQL_CURSOS)

    dev_num = desarrollador.isdigit() if desarrollador else False
    dev_txt = _fold(desarrollador) if (desarrollador and not dev_num) else None

    cmap: dict[int, list[dict]] = {}
    for c in cursos:
        cmap.setdefault(int(c["IdModulo"]), []).append(c)

    rows = []
    for mod in modulos:
        padres = cmap.get(int(mod["Id"]), [])
        if desarrollador:
            padres = [c for c in padres
                      if (dev_num and str(c["DevId"]) == desarrollador)
                      or (dev_txt and dev_txt in _fold(c["DevNombre"] or ""))]
            if not padres:
                continue

        horas_vivo = float(mod["HorasVivo"] or 0)
        sesiones = int(mod["SesionesVivo"] or 0)
        estimado = horas_vivo == 0 and sesiones > 0
        if estimado:
            horas_vivo = HORAS_SESION_ESTIMADA * sesiones
        horas = horas_vivo + async_horas
        horas_txt = f"{horas:g}" + ("*" if estimado else "")

        codigos = sorted({(c["Codigo"] or "").strip() or f"id:{c['ProductoId']}"
                          for c in padres})
        rows.append({
            "Docente": (mod["Docente"] or "").strip() or "(sin docente)",
            "Cursos": " / ".join(codigos) or "(sin curso padre)",
            "CodigoModulo": (mod["Codigo"] or "").strip(),
            "Modulo": (mod["Nombre"] or "").strip(),
            "Horas": horas_txt,
            "FechaInicio": str(mod["FechaInicio"]),
            "FechaFin": str(mod["FechaFin"]),
            "MontoUSD": "",
        })

    rows.sort(key=lambda r: (r["FechaFin"], r["Docente"]))
    return rows


def print_fichas(rows: list[dict], out_path: str | None) -> None:
    bloques = []
    for r in rows:
        bloques.append(
            f"NOMBRES Y APELLIDOS DEL DOCENTE: {r['Docente']}\n"
            f"- Código de curso: {r['Cursos']}\n"
            f"- Código y nombre de módulo: {r['CodigoModulo']} - {r['Modulo']}\n"
            f"- Horas: {r['Horas']}\n"
            f"- Fechas de dictado (inicio y fin): {r['FechaInicio']} al {r['FechaFin']}\n"
            f"- Monto (USD):"
        )
    text = "\n\n".join(bloques) + "\n"
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"wrote {len(rows)} fichas -> {out_path}", file=sys.stderr)
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser(
        description="Pagos a docentes: módulos que finalizan dictado en el mes, con horas y fechas (Monto en blanco).")
    ap.add_argument("--mes", type=mes_type, default=date.today().strftime("%Y-%m"),
                    help="Mes de finalización YYYY-MM (default: mes actual)")
    ap.add_argument("--desarrollador",
                    help="Filtra por encargado del curso padre (Producto.PersonalCreacion): Id numérico o substring del nombre.")
    ap.add_argument("--async-horas", type=float, default=2.0,
                    help="Horas asincrónicas a sumar a cada módulo (default: 2)")
    ap.add_argument("--fmt", choices=["table", "csv", "json", "fichas"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    rows = build_rows(args.mes, args.async_horas, args.desarrollador)

    scope = f" · dev~'{args.desarrollador}'" if args.desarrollador else ""
    print(f"\n>>> PAGOS A DOCENTES · módulos con última sesión en {args.mes}{scope} · "
          f"horas = en vivo + {args.async_horas:g}h async\n", file=sys.stderr)
    if not rows:
        print("Sin módulos que finalicen en ese mes con ese filtro.", file=sys.stderr)
        sys.exit(1)
    if any(r["Horas"].endswith("*") for r in rows):
        print("(*) Sesiones registradas con duración cero en Olympus; horas estimadas a "
              f"{HORAS_SESION_ESTIMADA}h por sesión — corregir el registro.\n", file=sys.stderr)

    if args.fmt == "fichas":
        print_fichas(rows, args.output)
    else:
        output(rows, fmt=args.fmt, out_path=args.output, headers=COLS)


if __name__ == "__main__":
    main()
