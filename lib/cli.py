"""
Helpers compartidos de argparse para los scripts de la skill.

Centraliza validadores y (Fase 3) los nombres canónicos de parámetros con
alias retro-compatibles, para que todos los scripts expongan la misma interfaz.
"""
from __future__ import annotations

import argparse
import re
from datetime import date

TOP_MAX = 500  # cota superior de filas pedibles con --top

_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def iso_date(value: str) -> str:
    """
    Valida fechas YYYY-MM-DD en argparse (reemplaza los regex ad-hoc por script).
    Valida también los rangos (2026-13-99 pasaba el regex y reventaba en SQL).
    """
    if not _ISO_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"debe ser YYYY-MM-DD, recibido {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fecha inexistente: {value!r}")
    return value


# Nombres canónicos de parámetros (Fase 3 del plan de limpieza):
#   --periodo        últimos N días (entero)
#   --desde/--hasta  ventana de fechas ISO ([desde, hasta), hasta exclusivo)
#   --top            filas a mostrar (ver top_type)
# Los nombres históricos (--since) quedan como alias para no romper invocaciones.


def add_desde(ap: argparse.ArgumentParser, default: str | None = None,
              help_text: str = "Fecha inicio inclusiva (YYYY-MM-DD)") -> None:
    """Registra --desde con alias retro-compatible --since."""
    ap.add_argument("--desde", "--since", dest="desde", type=iso_date,
                    default=default, help=f"{help_text} (alias: --since)")


def top_type(value: str) -> int:
    """Entero 1..TOP_MAX para --top (evita pedidos desmedidos a la BD)."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--top debe ser un entero, recibido {value!r}")
    if not 1 <= n <= TOP_MAX:
        raise argparse.ArgumentTypeError(f"--top debe estar entre 1 y {TOP_MAX}, recibido {n}")
    return n


def top_type_o_todas(value: str) -> int:
    """Como top_type pero acepta 0 = mostrar todas (para listados acotados)."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--top debe ser un entero, recibido {value!r}")
    if not 0 <= n <= TOP_MAX:
        raise argparse.ArgumentTypeError(f"--top debe estar entre 0 y {TOP_MAX} (0 = todas), recibido {n}")
    return n
