"""
Paquete lib de la skill olympus-crm-analytics.

Carga el .env de la raíz de la skill aquí para que CUALQUIER import de lib.*
(db, queries, calc, ...) vea las variables, sin depender del orden de imports.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
