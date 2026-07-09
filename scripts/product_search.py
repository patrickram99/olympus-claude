#!/usr/bin/env python3
"""
Búsqueda de productos por nombre o código de lanzamiento.

Uso:
  python scripts/product_search.py "key account"
  python scripts/product_search.py "imbpepkeyacc05261"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db, queries
from lib.format import output


def main():
    ap = argparse.ArgumentParser(description="Buscar productos por nombre o código")
    ap.add_argument("pattern", help="Patrón de búsqueda (LIKE %%pattern%%)")
    ap.add_argument("--fmt", choices=["table", "csv", "json"], default="table")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    like = f"%{args.pattern}%"
    raw = db.query(queries.SQL_PRODUCT_SEARCH, [like, like])
    # El identificador de negocio es el CodigoLanzamiento; el Id interno no se
    # muestra (fallback "id:N" solo para productos sin código asignado).
    rows = [{
        "Codigo": (r["CodigoLanzamiento"] or "").strip() or f"id:{r['Id']}",
        "Nombre": r["Nombre"],
        "CostoBase": r["CostoBase"],
        "EstadoProductoTipoId": r["EstadoProductoTipoId"],
        "FechaInicio": r["FechaInicio"],
    } for r in raw]
    print(f"\n>>> {len(rows)} productos coinciden con '{args.pattern}'\n", file=sys.stderr)
    output(rows, fmt=args.fmt, out_path=args.output)


if __name__ == "__main__":
    main()
