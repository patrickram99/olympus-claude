"""
Output helpers: pretty table to stdout, CSV writer.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Iterable

from tabulate import tabulate

# Windows consoles default to cp1252 and crash on unicode glyphs the tables use
# (→, —, ·, ≥). Force UTF-8 so scripts don't die with UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


def output(rows: list[dict], fmt: str = "table", out_path: str | None = None, headers: list[str] | None = None) -> None:
    """
    Emit `rows` (list of dicts) in the requested format.

    fmt: 'table' (default, stdout), 'csv', 'json'.
    out_path: if given, write to file; else stdout.
    headers: restrict to these keys (in this order).
    """
    if not rows:
        print("(no rows)", file=sys.stderr)
        return

    if headers:
        rows = [{h: r.get(h) for h in headers} for r in rows]
    else:
        headers = list(rows[0].keys())

    if fmt == "json":
        text = json.dumps(rows, default=str, indent=2, ensure_ascii=False)
        _emit(text, out_path)
        return

    if fmt == "csv":
        if out_path:
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                w.writerows(rows)
            print(f"wrote {len(rows)} rows -> {out_path}", file=sys.stderr)
        else:
            w = csv.DictWriter(sys.stdout, fieldnames=headers)
            w.writeheader()
            w.writerows(rows)
        return

    # default: table
    text = tabulate(rows, headers="keys", tablefmt="github", floatfmt=",.2f", numalign="right")
    _emit(text, out_path)


def _emit(text: str, out_path: str | None) -> None:
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"wrote -> {out_path}", file=sys.stderr)
    else:
        print(text)


def fmt_money(v: float, currency: str = "PEN") -> str:
    if v is None:
        return "—"
    return f"{currency} {v:,.2f}"


def fmt_pct(v: float, d: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{d}f}%"
