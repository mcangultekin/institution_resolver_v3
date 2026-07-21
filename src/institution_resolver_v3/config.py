"""config/default.yaml yukleyici (basit; okunmayan olu anahtar birakma - v2 O6)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


@lru_cache(maxsize=4)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _DEFAULT
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)
