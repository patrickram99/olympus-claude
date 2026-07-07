#!/usr/bin/env python3
"""
Campañas de LinkedIn (adm.LinkedIn_Lead.FormName) con el naming pattern decodificado.

FormName es el nombre legible de la campaña/formulario de LinkedIn — el único origen
con detalle de campaña (Oportunidad.Origen sólo dice "Linkedin"). Naming pattern:

    [FOR-] <FORMATO> <TEMA> [NIVEL] [SEGMENTO]

todo en MAYÚSCULAS, pegado, sin separadores. FORMATO ∈ {PAE, CEP, PEP, PAD}
(>94% de los leads). El prefijo FOR- es la variante "formulario" del mismo código.
Hay cola larga ad-hoc (WOMANLEAD, "PUENTES DE PAPEL", HABISITE2026…) sin patrón.

Uso:
  python scripts/linkedin_campanas.py                       # todas, top 50 por leads
  python scripts/linkedin_campanas.py --buscar Doc          # FormName LIKE %Doc%
  python scripts/linkedin_campanas.py --por-formato         # agrega por prefijo de formato
  python scripts/linkedin_campanas.py --min-leads 100 --top 30
  python scripts/linkedin_campanas.py --sin-test            # excluye TestLead=1
  python scripts/linkedin_campanas.py --fmt csv -o campanas.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output

FORMATOS = {"PAE", "CEP", "PEP", "PAD"}


def parse_formname(name: str) -> dict:
    """Descompone un FormName en {EsForm, Formato, Resto} según el naming pattern."""
    raw = (name or "").strip()
    es_form = raw.upper().startswith("FOR-")
    core = raw[4:] if es_form else raw
    prefijo = core[:3].upper()
    if prefijo in FORMATOS:
        return {"EsForm": "FOR-" if es_form else "", "Formato": prefijo, "Resto": core[3:]}
    return {"EsForm": "FOR-" if es_form else "", "Formato": "(otro)", "Resto": core}


def main():
    ap = argparse.ArgumentParser(description="Campañas LinkedIn por FormName con naming pattern")
    ap.add_argument("--buscar", help="Filtra FormName LIKE %%texto%% (case-insensitive)")
    ap.add_argument("--por-formato", action="store_true",
                    help="Agrega por FORMATO (PAE/CEP/PEP/PAD/otro) en vez de listar cada campaña")
    ap.add_argument("--min-leads", type=int, default=0, help="Excluir campañas con menos de N leads")
    ap.add_argument("--top", type=int, default=50, help="Mostrar las N con más leads (0 = todas)")
    ap.add_argument("--sin-test", action="store_true", help="Excluir TestLead=1")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    sql, params = queries.sql_linkedin_formnames(
        buscar=args.buscar, incluir_test=not args.sin_test
    )
    data = db.query(sql, params)

    enriched = []
    for r in data:
        leads = int(r["Leads"])
        if leads < args.min_leads:
            continue
        p = parse_formname(r["FormName"])
        enriched.append({
            "FormName": r["FormName"],
            "EsForm": p["EsForm"],
            "Formato": p["Formato"],
            "Resto": p["Resto"],
            "Leads": leads,
            "Primera": r["Primera"],
            "Ultima": r["Ultima"],
        })

    if args.por_formato:
        agg: dict[str, dict] = {}
        for e in enriched:
            a = agg.setdefault(e["Formato"], {"Formato": e["Formato"], "Campanas": 0, "Leads": 0})
            a["Campanas"] += 1
            a["Leads"] += e["Leads"]
        rows = sorted(agg.values(), key=lambda x: -x["Leads"])
        total = sum(x["Leads"] for x in rows) or 1
        for x in rows:
            x["%Leads"] = round(100.0 * x["Leads"] / total, 2)
        scope = f"buscar={args.buscar!r} · " if args.buscar else ""
        print(f"\n>>> Campañas LinkedIn por formato · {scope}{len(rows)} formatos\n", file=sys.stderr)
        output(rows, fmt=args.fmt, out_path=args.output)
        return

    rows = sorted(enriched, key=lambda x: -x["Leads"])
    if args.top and args.top > 0:
        rows = rows[: args.top]

    scope = f"LIKE %{args.buscar}% · " if args.buscar else ""
    print(f"\n>>> {len(rows)} campañas LinkedIn · {scope}{len(enriched)} totales tras filtros\n",
          file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
