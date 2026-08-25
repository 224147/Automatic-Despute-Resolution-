"""Loads config.yaml into a plain dict. Policy values live only in config.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).parent / "config.yaml"


def load_config(path: Path | str = _DEFAULT_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
