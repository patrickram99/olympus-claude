"""
Configuración de negocio de la skill (config.toml en la raíz).

Precedencia de cada parámetro: flag CLI (en el script) > variable de entorno
(.env) > config.toml > default de código. El .toml es la fuente editable por
negocio y se versiona; el .env queda para secretos y overrides locales.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent

_toml: dict = {}
_path = _ROOT / "config.toml"
if _path.exists():
    with open(_path, "rb") as f:
        _toml = tomllib.load(f)


def get(section: str, key: str, env_var: str | None, default: Any) -> Any:
    """Resuelve un parámetro de negocio con la precedencia env > toml > default."""
    if env_var:
        v = os.environ.get(env_var)
        if v is not None:
            return v
    return _toml.get(section, {}).get(key, default)


def get_float(section: str, key: str, env_var: str | None, default: float) -> float:
    return float(get(section, key, env_var, default))
