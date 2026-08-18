"""institution-field-inventory-resolved.csv'de resolved_* sutunlari BOS kalan
satirlari, ayni normalized_name'in kaynak veride BASKA bir satirda zaten
DOLU olan parent_name'iyle doldurur (batch/LLM koşusu YAPMADAN).

Arka plan:
  ~14.591 normalized_name, institution-field-inventory-normalized.csv
  icinde hem parent_name BOS hem parent_name DOLU satirlarla birlikte
  geciyor (ayni kurum, kaynakta bazen zaten cozulmus). Bu adlar butun
  batch ciktilarinda (temiz_sonuc.csv dahil) hic islenmemis - kuyruk
  bunlari atlamis. Ama zaten kaynakta tutarli (celiskisiz) bir parent_name
  bilgisi var, o yuzden LLM/gate'e sokmaya gerek yok.

Kural:
  - Sadece resolved_parent_match BOS + resolved_parent_name BOS + parent_name
    BOS olan satirlar hedef alinir (islenmemis satirlar).
  - normalized_name (normalized dosyasindan, POZISYONEL hizalamayla alinir)
    icin kaynakta baska satirlarda DOLU ve TUTARLI (tek deger) bir
    parent_name varsa: resolved_parent_name doldurulur,
    resolved_parent_match = 'source_backfill' isaretlenir.
  - resolved_parent_id BILEREK BOS birakilir (inventory CSV'nin parent_id'si
    katalogla ayni id uzayinda degil - v2_canonical_id/csv_id_uzayi
    notlarina bkz). Ad bilgisi var, id bilgisi yok.
  - Celiskili (birden fazla farkli parent_name degeri) adlar HIC
    dokunulmadan atlanir - guvenli tarafta kal.

Cikti: institution-field-inventory-resolved.csv'yi YERINDE degil, ayri bir
dosyaya yazar (varsayilan: institution-field-inventory-resolved-backfilled.csv).
Orijinal dosyaya DOKUNULMAZ.

Kullanim:
    python3 scripts/backfill_resolved_from_source_parent.py
"""

from __future__ import annotations

import csv
from pathlib import Path

csv.field_size_limit(10_000_000)

NORMALIZED = Path("data/inventory/normalized.csv")
RESOLVED = Path("data/inventory/resolved-llm-only.csv")
OUT = Path("data/inventory/institution-field-inventory-resolved-backfilled.csv")

BACKFILL_LABEL = "source_backfill"


def _build_lookup() -> dict[str, str]:
    """normalized_name -> parent_name (sadece tutarli/tek-degerli olanlar)."""
    values: dict[str, set[str]] = {}
    with NORMALIZED.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["normalized_name"]
            parent = row["parent_name"]
            if name and parent:
                values.setdefault(name, set()).add(parent)

    lookup = {name: next(iter(vals)) for name, vals in values.items() if len(vals) == 1}
    n_conflict = sum(1 for vals in values.values() if len(vals) > 1)
    print(f"  -> {len(lookup):,} benzersiz normalized_name (tutarli parent_name)")
    print(f"  -> {n_conflict:,} celiskili normalized_name (atlandi)")
    return lookup


def main() -> None:
    print(f"kaynak parent_name sozlugu kuruluyor: {NORMALIZED}")
    lookup = _build_lookup()

    n_total = 0
    n_target = 0  # resolved_* + parent_name hepsi bos olan satirlar
    n_filled = 0

    with NORMALIZED.open(newline="", encoding="utf-8") as fn, \
         RESOLVED.open(newline="", encoding="utf-8") as fr, \
         OUT.open("w", newline="", encoding="utf-8") as fout:
        reader_n = csv.DictReader(fn)
        reader_r = csv.DictReader(fr)
        writer = csv.DictWriter(fout, fieldnames=reader_r.fieldnames)
        writer.writeheader()

        for row_n, row_r in zip(reader_n, reader_r):
            n_total += 1

            # pozisyonel hizalama guvenligi: ayni satir oldugunu dogrula
            key_n = (row_n["object_class"], row_n["object_id"], row_n["field_name"])
            key_r = (row_r["object_class"], row_r["object_id"], row_r["field_name"])
            if key_n != key_r:
                raise RuntimeError(
                    f"satir {n_total}: normalized/resolved dosyalari hizasiz "
                    f"({key_n} != {key_r})"
                )

            is_target = (
                not row_r["parent_name"]
                and not row_r["resolved_parent_name"]
                and not row_r["resolved_parent_match"]
            )
            if is_target:
                n_target += 1
                hit = lookup.get(row_n["normalized_name"])
                if hit is not None:
                    row_r["resolved_parent_name"] = hit
                    row_r["resolved_parent_match"] = BACKFILL_LABEL
                    n_filled += 1

            writer.writerow(row_r)

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir                 : {n_total:,}")
    print(f"islenmemis (hedef) satir     : {n_target:,}")
    print(f"  -> kaynaktan dolduruldu    : {n_filled:,}")
    print(f"  -> hala bos (celiski/yok)  : {n_target - n_filled:,}")


if __name__ == "__main__":
    main()
