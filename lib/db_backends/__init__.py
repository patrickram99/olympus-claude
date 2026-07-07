"""
Backends de base de datos por proveedor.

Olympus corre hoy en SQL Server pero migrará a PostgreSQL: todo lo específico
del proveedor (driver, connection string, TLS/certificados, estilo de
placeholders) vive en el backend correspondiente, no en lib/db.py ni en los
scripts. Se selecciona con la env var DB_DIALECT (default: mssql).

Contrato de un backend (módulo):
  - connect() -> conexión DB-API 2.0 (lanza SystemExit(2) si falta config)
  - translate_sql(sql: str) -> str  (adapta placeholders/dialecto si hace falta)
"""
from __future__ import annotations

import sys


def get_backend(dialect: str):
    dialect = (dialect or "mssql").strip().lower()
    if dialect == "mssql":
        from . import mssql
        return mssql
    if dialect in ("postgres", "postgresql", "pg"):
        from . import postgres
        return postgres
    print(f"ERROR: DB_DIALECT desconocido: {dialect!r} (soportados: mssql, postgres)", file=sys.stderr)
    sys.exit(2)
