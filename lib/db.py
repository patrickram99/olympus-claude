"""
DB connection helper for Olympus (capa de abstracción de proveedor).

El proveedor se elige con DB_DIALECT (default: mssql; postgres queda como stub
para la migración). Todo lo específico del proveedor — driver, connection
string, TLS/certificados, placeholders — vive en lib/db_backends/<dialecto>.py.

Loads .env from the skill root and exposes:
  - get_connection() -> DB-API connection
  - query(sql, params=None) -> list[dict]
  - query_scalar(sql, params=None) -> any
  - query_one(sql, params=None) -> dict | None
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from .db_backends import get_backend

# Load .env from the package root (parent of lib/)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

_backend = get_backend(os.environ.get("DB_DIALECT", "mssql"))

_connection = None


def get_connection():
    """Lazy singleton connection. Reconnects on next call if broken."""
    global _connection
    if _connection is None:
        _connection = _backend.connect()
    return _connection


def query(sql: str, params: Iterable[Any] | None = None) -> list[dict]:
    """Run a SELECT and return all rows as a list of dicts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(_backend.translate_sql(sql), params or [])
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def query_scalar(sql: str, params: Iterable[Any] | None = None) -> Any:
    """Return the first cell of the first row, or None."""
    rows = query(sql, params)
    if not rows:
        return None
    return next(iter(rows[0].values()))


def query_one(sql: str, params: Iterable[Any] | None = None) -> dict | None:
    """Return the first row as a dict, or None."""
    rows = query(sql, params)
    return rows[0] if rows else None
