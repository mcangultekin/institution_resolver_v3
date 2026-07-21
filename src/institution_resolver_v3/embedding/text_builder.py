"""Kanonik kayit -> embed metni (e5 icin doğal metin).

Kanitli iki kazanim korunur: TUM alias'lar (ceviri eslesmesi) + subunit'e
PARENT-adi enjeksiyonu. Metin DOGAL (case+aksan korunur) - e5 modeli boyle
ister; agresif normalize embedding kalitesini dusurur.

Format:  "passage: {ad} - {parent_adi (subunit)} - {alias'lar}"
Dedup: ayni ismin (normalize seviyesinde) tekrari atilir (ad zaten alias'ta olabilir).
"""

from __future__ import annotations

from typing import Any

from institution_resolver_v3.config import load_config
from institution_resolver_v3.normalize.query_pipeline import normalize


def _passage_prefix() -> str:
    return load_config()["embedding"]["passage_prefix"]


def _dedup_key(text: str) -> str:
    return normalize(text).base_no_accent


def build_embed_text(
    record: dict[str, Any],
    parent_names: dict[str, str],
    *,
    prefix: str | None = None,
) -> str:
    """Kayit dict'inden embed metni uretir (dogal metin, prefix'li)."""
    prefix = _passage_prefix() if prefix is None else prefix
    parts: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        if not value:
            return
        k = _dedup_key(value)
        if k and k not in seen:
            seen.add(k)
            parts.append(value.strip())

    add(record["name"])
    if record.get("record_type") == "subunit":
        add(parent_names.get(record.get("parent_id"), ""))     # PARENT ENJEKSIYONU
    for a in record.get("aliases", []):
        add(a.get("value", ""))

    return prefix + " - ".join(parts)
