"""
Helpers compartidos de argparse para los scripts de la skill.

Centraliza validadores y (Fase 3) los nombres canónicos de parámetros con
alias retro-compatibles, para que todos los scripts expongan la misma interfaz.
"""
from __future__ import annotations

import argparse

TOP_MAX = 500  # cota superior de filas pedibles con --top


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
