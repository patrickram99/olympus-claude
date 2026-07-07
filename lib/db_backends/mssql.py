"""
Backend SQL Server (pyodbc). Proveedor actual de Olympus.

La configuración TLS (Encrypt / TrustServerCertificate) vive aquí: si cambia
el proveedor o el certificado del servidor, este es el único archivo a tocar.
"""
from __future__ import annotations

import os
import sys

import pyodbc


def _conn_str() -> str:
    server = os.environ.get("DB_SERVER")
    port = os.environ.get("DB_PORT", "1433")
    db = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    pwd = os.environ.get("DB_PASSWORD")
    driver = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    encrypt = os.environ.get("DB_ENCRYPT", "yes")
    # El servidor usa certificado self-signed; mientras sea así se necesita
    # TrustServerCertificate=yes para conectar con Encrypt=yes.
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


def connect():
    return pyodbc.connect(_conn_str(), timeout=30)


def translate_sql(sql: str) -> str:
    """Las queries de la skill usan placeholders '?' (estilo pyodbc): sin cambios."""
    return sql
