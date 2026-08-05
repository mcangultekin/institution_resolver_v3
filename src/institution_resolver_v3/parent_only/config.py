"""Parent-only ayarlari - config/default.yaml'daki OPSIYONEL `parent_only:` blogu.

Blok yoksa her deger makul bir varsayilana duser, yani `config/default.yaml`
DEGISTIRILMEDEN calisir (bu modun kurali: mevcut dosyalara dokunma). Ayar
gerekince blok elle eklenir:

    parent_only:
      garbage_lexical_floor: 0.55   # yoksa gate.garbage_lexical_floor, o da yoksa 0.55
      max_span: null                # null = sinirsiz (bkz. __init__.py "SPAN SINIRI")
      max_candidates: 8             # hakeme giden aday sayisi ust siniri
      generic_name_threshold: 3     # jenerik-ad korumasi (bkz. genericity.py); 0 = kapali
"""

from __future__ import annotations

from typing import Any

DEFAULT_FLOOR = 0.55
DEFAULT_MAX_CANDIDATES = 8
# Adi katalogda bu kadar (>=) baska kayit adinin icinde gecen bir aday `auto_match`
# olamaz - hakeme yonlendirilir. Olculdu (460 satir, 2026-08-05): esik 3'te 11
# supheli auto'nun 10'u yakalaniyor, bedeli 6 ek LLM cagrisi (LLM orani
# %38.0 -> %41.5). Esik 1 kullanilamaz (96 satir yonlendirir - neredeyse her Turk
# universitesi c=1 aliyor); 3 ile 10 arasi sonuc az degisir (10/11 -> 9/11).
DEFAULT_GENERIC_NAME_THRESHOLD = 3


def _block(config: dict[str, Any] | None) -> tuple[dict, dict]:
    if config is None:
        from institution_resolver_v3.config import load_config

        config = load_config()
    return (config.get("parent_only") or {}), (config.get("gate") or {})


def floor_tsr(config: dict[str, Any] | None = None) -> float:
    """Cop kapisi esigi. Parent-only kendi esigini tasiyabilir (gold gelince ayri
    kalibre edilecek); yoksa gate'in esigine, o da yoksa 0.55'e duser."""
    po, gate = _block(config)
    if "garbage_lexical_floor" in po:
        return float(po["garbage_lexical_floor"])
    return float(gate.get("garbage_lexical_floor", DEFAULT_FLOOR))


def max_span(config: dict[str, Any] | None = None) -> int | None:
    """decompose pencere uzunlugu siniri. None = sinirsiz (varsayilan)."""
    po, _ = _block(config)
    v = po.get("max_span")
    return None if v is None else int(v)


def max_candidates(config: dict[str, Any] | None = None) -> int:
    """Hakeme giden aday listesi ust siniri (havuzun kendisi ETKILENMEZ)."""
    po, _ = _block(config)
    return int(po.get("max_candidates", DEFAULT_MAX_CANDIDATES))


def generic_name_threshold(config: dict[str, Any] | None = None) -> int:
    """Jenerik-ad korumasinin esigi. 0 (ya da negatif) = koruma KAPALI."""
    po, _ = _block(config)
    return int(po.get("generic_name_threshold", DEFAULT_GENERIC_NAME_THRESHOLD))
