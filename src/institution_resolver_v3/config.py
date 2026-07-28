"""config/default.yaml yukleyici (basit; okunmayan olu anahtar birakma - v2 O6)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


@lru_cache(maxsize=4)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    # INRES3_CONFIG: Docker/prod'da ES/Ollama host'lari localhost degil servis
    # adi oldugu icin (bkz. config/docker.yaml) - set edilmezse eski davranis.
    p = Path(path) if path else Path(os.environ.get("INRES3_CONFIG", _DEFAULT))
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)
