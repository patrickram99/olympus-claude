"""
Backend PostgreSQL (stub). Proveedor futuro de Olympus.

Pendiente para la migración:
  1. Dependencia: psycopg[binary] en requirements.txt.
  2. connect(): psycopg.connect() con DB_SERVER/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
     y TLS vía DB_SSLMODE (default "require") + DB_SSLROOTCERT opcional —
     el certificado/SSL vive aquí, igual que Encrypt/Trust vive en mssql.py.
  3. translate_sql(): psycopg usa '%s' como placeholder; la traducción '?' -> '%s'
     de abajo ya lo cubre (las queries de la skill no contienen '?' literales).
  4. Dialecto: revisar el inventario de construcciones T-SQL (TOP, DATEADD,
     GETDATE, ISNULL, CONVERT) documentado en references/ y portarlas a ANSI.
"""
from __future__ import annotations

import sys


def connect():
    print(
        "ERROR: el backend postgres aún no está implementado (la migración de "
        "Olympus a PostgreSQL está pendiente). Usa DB_DIALECT=mssql.",
        file=sys.stderr,
    )
    sys.exit(2)


def translate_sql(sql: str) -> str:
    return sql.replace("?", "%s")
