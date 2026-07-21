"""`data/raw/*.csv` -> düz dict listesi (salt okunur, hiçbir dönüşüm yok).

stdlib `csv` ile okunur; pandas gibi ek ağır bağımlılık gerektirmez. Bu modül
CSV metnini olduğu gibi ayrıştırır - qualifier soyma, aktif filtresi, klon
birleştirme gibi TÜM iş mantığı `canonicalize.py`'de, saf fonksiyonlar olarak
yaşar.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _parse_aliases(raw_json: str) -> list[dict[str, Any]]:
    if not raw_json:
        return []
    doc = json.loads(raw_json)
    items = doc.get("items", [])
    aliases: list[dict[str, Any]] = []
    for item in items:
        name = item.get("name")
        if not name:
            continue
        aliases.append(
            {
                "value": name,
                "locale": item.get("locale"),
                "source": item.get("source"),
            }
        )
    return aliases


def _parse_active(value: str) -> bool:
    return value.strip().lower() == "true"


def load_parent_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            rows.append(
                {
                    "id": raw["id"],
                    "name": raw["name"],
                    "country": raw.get("country") or None,
                    "city": raw.get("city") or None,
                    "canonical_ref": raw.get("canonical_ref") or None,
                    "active": _parse_active(raw["active"]),
                    "aliases": _parse_aliases(raw.get("aliases", "")),
                }
            )
    return rows


def load_subunit_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            rows.append(
                {
                    "id": raw["id"],
                    "parent_id": raw.get("parent_id") or None,
                    "name": raw["name"],
                    "kind_label": raw.get("kind_label") or None,
                    "active": _parse_active(raw["active"]),
                    "aliases": _parse_aliases(raw.get("aliases", "")),
                }
            )
    return rows
