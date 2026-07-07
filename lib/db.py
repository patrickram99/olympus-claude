"""
DB connection helper for Olympus SQL Server.

Loads .env from the skill root and exposes:
  - get_connection() -> pyodbc.Connection
  - query(sql, params=None) -> list[dict]
  - query_scalar(sql, params=None) -> any
  - query_one(sql, params=None) -> dict | None
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pyodbc
from dotenv import load_dotenv

# Load .env from the package root (parent of lib/)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _conn_str() -> str:
    server = os.environ.get("DB_SERVER")
    port = os.environ.get("DB_PORT", "1433")
    db = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    pwd = os.environ.get("DB_PASSWORD")
    driver = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    encrypt = os.environ.get("DB_ENCRYPT", "yes")
    trust = os.environ.get("DB_TRUST_SERVER_CERT", "yes")
    missing = [k for k, v in {"DB_SERVER": server, "DB_NAME": db, "DB_USER": user, "DB_PASSWORD": pwd}.items() if not v]
    if missing:
        print(f"ERROR: faltan variables en .env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={pwd};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust};"
    )


_connection: pyodbc.Connection | None = None


def get_connection() -> pyodbc.Connection:
    """Lazy singleton connection. Reconnects on next call if broken."""
    global _connection
    if _connection is None:
        _connection = pyodbc.connect(_conn_str(), timeout=30)
    return _connection


def query(sql: str, params: Iterable[Any] | None = None) -> list[dict]:
    """Run a SELECT and return all rows as a list of dicts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params or [])
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
