"""[ESKI - KULLANILMIYOR] Ilk normalize denemesi.

Bu dosyanin isi artik query_pipeline.py'de (turkish_lower + strip_turkish_accents)
daha kapsamli sekilde yapiliyor. Referans olarak duruyor, yeni kodda kullanma.

--- orijinal docstring ---
Turkce'ye ozgu ascii-fold + kucuk harf donusumu.

v2'nin `normalize/query_pipeline.turkish_lower` fonksiyonundan BAGIMSIZ,
kendi kucuk implementasyonumuz (bkz. CLAUDE.md: v3, v2 kodundan import etmez).
Python'in yerlesik `str.lower()` Turkce 'İ' (U+0130) icin bilesik karakter
uretir ("İ".lower() == "i̇", iki kod noktasi) - bu da asagi akista (JSONL
kanonik anahtar, birlestirme anahtari) sessizce hatali eslesmelere yol acar.
Bu yuzden Turkce harfleri once ASCII'ye katlıyoruz, sonra `str.lower()`
uyguluyoruz.
"""

from __future__ import annotations

import re

_FOLD_MAP = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ğ": "g",
        "ğ": "g",
        "Ü": "u",
        "ü": "u",
        "Ş": "s",
        "ş": "s",
        "Ö": "o",
        "ö": "o",
        "Ç": "c",
        "ç": "c",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def fold_turkish(text: str) -> str:
    """ASCII-katlanmis, kucuk harfli, tek-bosluklu metin. Noktalama korunur."""
    return normalize_whitespace(text.translate(_FOLD_MAP).lower())
