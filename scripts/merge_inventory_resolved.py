"""institution-field-inventory.csv'ye temiz_sonuc.csv kararlarini yeni
sutunlar olarak ekler. Orijinal dosyaya DOKUNULMAZ, ayri bir cikti CSV'si
yazilir.

Kural:
  - parent_name BOS olan satirlar -> normalized_name ile temiz_sonuc.csv'de
    aranir; bulunursa resolved_* sutunlari doldurulur (match=no_match/review
    olsa bile etiket yazilir, id/ad bos kalir).
  - parent_name DOLU olan satirlar -> resolved_* sutunlari tamamen bos
    birakilir (hic arama yapilmaz).
  - normalized_name temiz_sonuc.csv'de hic yoksa (batch disi kalmis ad)
    -> resolved_* sutunlari tamamen bos kalir (islenmedi anlamina gelir,
    no_match'ten ayirt edilir).

Kullanim:
    python3 scripts/merge_inventory_resolved.py
"""

from __future__ import annotations

import csv
from pathlib import Path

csv.field_size_limit(10_000_000)

INVENTORY_NORMALIZED = Path("data/inventory/normalized.csv")
TEMIZ_SONUC = Path("main_batch/temiz_sonuc.csv")
OUT = Path("data/inventory/resolved-llm-only.csv")

NEW_COLS = [
    "resolved_parent_id",
    "resolved_parent_name",
    "resolved_parent_match",
    "resolved_subunit_id",
    "resolved_subunit_name",
    "resolved_subunit_match",
]


def _load_temiz_sonuc(path: Path) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            norm = row["normalized_name"]
            if norm in lookup:
                continue  # tek istisna: bos normalized_name grubu, hepsi no_match
            lookup[norm] = {
                "resolved_parent_id": row.get("parent_id", ""),
                "resolved_parent_name": row.get("parent", ""),
                "resolved_parent_match": row.get("parent_match", ""),
                "resolved_subunit_id": row.get("subunit_id", ""),
                "resolved_subunit_name": row.get("subunit", ""),
                "resolved_subunit_match": row.get("subunit_match", ""),
            }
    return lookup


def main() -> None:
    print(f"temiz_sonuc.csv okunuyor: {TEMIZ_SONUC}")
    lookup = _load_temiz_sonuc(TEMIZ_SONUC)
    print(f"  -> {len(lookup):,} benzersiz normalized_name")

    n_total = 0
    n_parent_empty = 0
    n_filled = 0
    n_unmatched_batch = 0  # parent bos ama normalized_name temiz_sonuc'ta yok

    with INVENTORY_NORMALIZED.open(newline="", encoding="utf-8") as fin, \
         OUT.open("w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        base_fields = [c for c in reader.fieldnames if c != "normalized_name"]
        writer = csv.DictWriter(fout, fieldnames=base_fields + NEW_COLS)
        writer.writeheader()

        for row in reader:
            n_total += 1
            out_row = {k: row[k] for k in base_fields}
            for col in NEW_COLS:
                out_row[col] = ""

            if not row["parent_name"]:
                n_parent_empty += 1
                hit = lookup.get(row["normalized_name"])
                if hit is not None:
                    out_row.update(hit)
                    n_filled += 1
                else:
                    n_unmatched_batch += 1

            writer.writerow(out_row)

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir            : {n_total:,}")
    print(f"parent bos satir        : {n_parent_empty:,}")
    print(f"  -> temiz_sonuc'ta bulundu (dolduruldu): {n_filled:,}")
    print(f"  -> batch disi (bos kaldi)              : {n_unmatched_batch:,}")


if __name__ == "__main__":
    main()
