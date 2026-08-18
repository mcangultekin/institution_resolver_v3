"""Butun oturumun sonucunu tek, sade bir CSV'de toplar - kullanicinin
istedigi sema (2026-08-18):

  current_institution_name, normalized_name, parent_name, parent_id,
  kaynak, parent_match, subunit_name, subunit_id, subunit_match

Satir sayisi = ham veri kadar (8.920.512) - benzersizlestirme YOK, ana
CSV'deki sirayla.

Birlestirme kurallari:
  parent_name / parent_id:
    resolved_parent_match DOLUYSA (LLM VEYA bu oturumdaki tum manuel
    baglamalar - katalog isim-eslemesi, MEB, askeri, rename, mukerrer-
    katalog - hepsi resolved_parent_* sutunlarina zaten yazildi) -> o
    kullanilir. BOSSA -> ham parent_name (kataloga baglanamamis 9.286
    satirin ham adi) kullanilir.
  parent_match:
    resolved_parent_match doluysa dogrudan o (match/no_match/review/
    judge_error). BOSSA ama ham parent_name doluysa -> 'review' (ad
    biliniyor, kataloga baglanamadi).
  kaynak (ror/yok):
    parent_id'nin parent_canonical.jsonl'deki canonical_ref alaninin
    on eki ('ror:...' -> 'ror', 'yok:...' -> 'yok'). parent_id yoksa bos.
  subunit_name / subunit_id:
    SADECE resolved_subunit_name / resolved_subunit_id - ham subunit_name
    KULLANILMIYOR (kullanici karari: ham subunit bizim subunit kataloguyla
    hizali degil).
  subunit_match:
    resolved_subunit_match doluysa dogrudan o. BOSSA:
      - current_institution_name'de alt-birim ifadesi (fakulte/bolum/
        enstitu/yuksekokul/program/anabilim dali/bilim dali/uygulama ve
        arastirma) geciyorsa -> 'review' (girdi subunit icerir gibi
        gorunuyor ama cozulmemis)
      - gecmiyorsa -> 'yok' (girdide zaten subunit yok, normal durum)
    Bu kural 500K+2M satirlik ornekte dogrulandi: kelime-yok grubunun
    %99,88'i gercekten subunit'siz kurum adi.

Girdiler: institution-field-inventory-normalized-backfilled.csv,
          institution-field-inventory-resolved-final3.csv,
          data/processed/parent_canonical.jsonl
Cikti: institution-field-inventory-summary.csv (yeni dosya)

Kullanim:
    python3 scripts/build_final_summary_csv.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

csv.field_size_limit(10_000_000)

NORMALIZED_BACKFILLED = Path("data/inventory/normalized-backfilled.csv")
RESOLVED = Path("data/inventory/resolved-merged.csv")
CATALOG = Path("data/processed/parent_canonical.jsonl")
OUT = Path("data/inventory/summary.csv")

SUBUNIT_KEYWORDS = [
    "fakülte", "fakulte", "bölüm", "bolum", "enstitü", "enstitu",
    "yüksekokul", "yuksekokul", "program", "pr.", "myo",
    "anabilim dal", "ana bilim dal", "bilim dal",
    "uygulama ve araştırma", "uygulama ve arastirma",
]

OUT_FIELDS = [
    "current_institution_name", "normalized_name",
    "parent_name", "parent_id", "kaynak", "parent_match",
    "subunit_name", "subunit_id", "subunit_match",
]


def _has_subunit_keyword(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in SUBUNIT_KEYWORDS)


def _build_source_lookup() -> dict[str, str]:
    """katalog id -> 'ror' | 'yok' | '' (canonical_ref onekinden)."""
    lookup: dict[str, str] = {}
    with CATALOG.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ref = rec.get("canonical_ref") or ""
            prefix = ref.split(":", 1)[0] if ":" in ref else ""
            lookup[rec["id"]] = prefix
    return lookup


def main() -> None:
    print("katalog kaynak (ror/yok) sozlugu kuruluyor...")
    source_lookup = _build_source_lookup()

    n_total = 0

    with NORMALIZED_BACKFILLED.open(newline="", encoding="utf-8") as fn, \
         RESOLVED.open(newline="", encoding="utf-8") as fr, \
         OUT.open("w", newline="", encoding="utf-8") as fout:
        reader_n = csv.DictReader(fn)
        reader_r = csv.DictReader(fr)
        writer = csv.DictWriter(fout, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for row_n, row_r in zip(reader_n, reader_r):
            n_total += 1

            key_n = (row_n["object_class"], row_n["object_id"], row_n["field_name"])
            key_r = (row_r["object_class"], row_r["object_id"], row_r["field_name"])
            if key_n != key_r:
                raise RuntimeError(f"satir {n_total}: dosyalar hizasiz ({key_n} != {key_r})")

            # --- parent ---
            if row_r["resolved_parent_match"]:
                parent_name = row_r["resolved_parent_name"]
                parent_id = row_r["resolved_parent_id"]
                parent_match = row_r["resolved_parent_match"]
            elif row_n["parent_name"]:
                parent_name = row_n["parent_name"]
                parent_id = ""
                parent_match = "review"
            else:
                parent_name = ""
                parent_id = ""
                parent_match = ""

            kaynak = source_lookup.get(parent_id, "") if parent_id else ""

            # --- subunit ---
            subunit_name = row_r["resolved_subunit_name"]
            subunit_id = row_r["resolved_subunit_id"]
            if row_r["resolved_subunit_match"]:
                subunit_match = row_r["resolved_subunit_match"]
            elif _has_subunit_keyword(row_n["current_institution_name"]):
                subunit_match = "review"
            else:
                subunit_match = "yok"

            writer.writerow({
                "current_institution_name": row_n["current_institution_name"],
                "normalized_name": row_n["normalized_name"],
                "parent_name": parent_name,
                "parent_id": parent_id,
                "kaynak": kaynak,
                "parent_match": parent_match,
                "subunit_name": subunit_name,
                "subunit_id": subunit_id,
                "subunit_match": subunit_match,
            })

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir: {n_total:,}")


if __name__ == "__main__":
    main()
