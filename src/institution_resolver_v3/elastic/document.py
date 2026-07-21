"""Kanonik kayit -> ES belgesi (arama gorunumu).

Payload (tam bilgi) ile arama gorunumu ayni belgede, id ile bagli. ES'e giden
metin alanlarina AGRESIF normalize UYGULANMAZ - ES analyzer'i index aninda folder
(bkz. mappings.py). Bizim isimiz: alias'lari birlestir + subunit'e parent adini
enjekte et.

Parent-adi enjeksiyonu (kanitli kazanim): "istatistik bolumu" 100+ universitede
var; subunit belgesine parent adi eklenince "gazi istatistik" dogru kaydi bulur.
"""

from __future__ import annotations

from typing import Any


def _alias_values(record: dict[str, Any]) -> list[str]:
    """Alias degerlerini dedup'layarak (gorunum sirasi korunur) dondurur."""
    seen: set[str] = set()
    out: list[str] = []
    for a in record.get("aliases", []):
        v = a.get("value")
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def build_document(
    record: dict[str, Any],
    parent_names: dict[str, str],
) -> dict[str, Any]:
    """Kanonik kayit dict'ini ES belge dict'ine cevirir.

    `parent_names`: {parent_id -> parent adi}. Subunit'e enjekte etmek icin.
    Doner: `_id` haric ES kaynak belgesi (indexer `_id`'yi record["id"]'den verir).
    """
    rt = record["record_type"]
    aliases_text = " ".join(_alias_values(record))

    doc: dict[str, Any] = {
        "id": record["id"],
        "record_type": rt,
        "name": record["name"],
        "normalized_name": record.get("normalized_name"),
        "aliases_text": aliases_text,
    }

    if rt == "parent":
        doc["country"] = record.get("country")
        doc["city"] = record.get("city")
        doc["canonical_ref"] = record.get("canonical_ref")
        doc["active_override"] = bool(record.get("active_override", False))
    else:  # subunit
        parent_id = record.get("parent_id")
        doc["parent_id"] = parent_id
        doc["merged_ids"] = record.get("merged_ids", [record["id"]])
        doc["parent_name"] = parent_names.get(parent_id, "")     # ENJEKSIYON
        doc["kind_label_raw"] = record.get("kind_label_raw")
        doc["unit_type"] = record.get("unit_type")
        doc["program_type"] = record.get("program_type")
        doc["is_interdisciplinary"] = bool(record.get("is_interdisciplinary", False))
        doc["is_evening"] = bool(record.get("is_evening", False))
        doc["is_ror_child"] = bool(record.get("is_ror_child", False))

    return doc


def build_parent_name_index(parent_records: list[dict[str, Any]]) -> dict[str, str]:
    """{parent_id -> ad} indeksi (subunit enjeksiyonu icin)."""
    return {r["id"]: r["name"] for r in parent_records}
