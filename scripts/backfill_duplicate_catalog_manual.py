"""Katalogda (parent_canonical.jsonl) MUKERRER kayitli 15 kurumu YOK
kaynakli id'ye baglar - normalize edilince bu isimler iki farkli id'ye
denk geliyordu (ROR kaynakli uluslararasi kayit + YOK kaynakli Turkce
kayit, hic birlestirilmemis - bkz. her ciftin canonical_ref alani).

Kullanici karari (2026-08-18): YOK kaynakli id secildi - ham envanter
verimiz Turkiye kaynakli oldugu icin YOK kaydiyla daha tutarli.

Girdi: bir onceki adimin ciktisi
  institution-field-inventory-resolved-final2.csv
(MEB + askeri + rename manuel baglama tamamlanmis versiyon)

Cikti: institution-field-inventory-resolved-final3.csv (yeni dosya, girdi
DEGISTIRILMEZ).

Kullanim:
    python3 scripts/backfill_duplicate_catalog_manual.py
"""

from __future__ import annotations

import csv
from pathlib import Path

csv.field_size_limit(10_000_000)

NORMALIZED_BACKFILLED = Path("data/inventory/normalized-backfilled.csv")
RESOLVED_IN = Path("data/inventory/institution-field-inventory-resolved-final2.csv")
OUT = Path("data/inventory/resolved-merged.csv")

# ham_ad -> (YOK kaynakli katalog id, katalog adi)
DUPLICATE_MAP: dict[str, tuple[str, str]] = {
    "ADA KENT UNIVERSITY": ("219", "ADA KENT ÜNİVERSİTESİ"),
    "KIRGIZİSTAN-TÜRKİYE MANAS ÜNİVERSİTESİ": ("258", "KIRGIZİSTAN-TÜRKİYE MANAS ÜNİVERSİTESİ"),
    "SÜLEYMAN DEMİREL ÜNİVERSİTESİ": ("206", "SÜLEYMAN DEMİREL ÜNİVERSİTESİ"),
    "DOĞU AKDENİZ ÜNİVERSİTESİ": ("394", "DOĞU AKDENİZ ÜNİVERSİTESİ"),
    "YAKIN DOĞU ÜNİVERSİTESİ": ("187", "YAKIN DOĞU ÜNİVERSİTESİ"),
    "ULUSLARARASI KIBRIS ÜNİVERSİTESİ": ("311", "ULUSLARARASI KIBRIS ÜNİVERSİTESİ"),
    "GİRNE AMERİKAN ÜNİVERSİTESİ": ("171", "GİRNE AMERİKAN ÜNİVERSİTESİ"),
    "Uluslararası Final Üniversitesi": ("349", "ULUSLARARASI FİNAL ÜNİVERSİTESİ"),
    "ULUSLARARASI SARAYBOSNA ÜNİVERSİTESİ": ("156", "ULUSLARARASI SARAYBOSNA ÜNİVERSİTESİ"),
    "GİRNE ÜNİVERSİTESİ": ("327", "GİRNE ÜNİVERSİTESİ"),
    "AZERBAIJAN MEDICAL UNIVERSITY": ("200", "AZERBAYCAN TIP ÜNİVERSİTESİ"),
    "INTERNATIONAL BALKAN UNIVERSITY": ("92", "ULUSLARARASI BALKAN ÜNİVERSİTESİ"),
    "Ivane Javakhishvili Tbilisi State University": ("286", "İVANE JAVAKHİSHVİLİ TİFLİS DEVLET ÜNİVERSİTESİ"),
    "COMRAT STATE UNIVERSITY": ("298", "KOMRAT DEVLET ÜNİVERSİTESİ"),
    "AKDENİZ KARPAZ ÜNİVERSİTESİ": ("137", "AKDENİZ KARPAZ ÜNİVERSİTESİ"),
}


def main() -> None:
    n_total = 0
    n_filled = 0

    with NORMALIZED_BACKFILLED.open(newline="", encoding="utf-8") as fn, \
         RESOLVED_IN.open(newline="", encoding="utf-8") as fr, \
         OUT.open("w", newline="", encoding="utf-8") as fout:
        reader_n = csv.DictReader(fn)
        reader_r = csv.DictReader(fr)
        writer = csv.DictWriter(fout, fieldnames=reader_r.fieldnames)
        writer.writeheader()

        for row_n, row_r in zip(reader_n, reader_r):
            n_total += 1

            key_n = (row_n["object_class"], row_n["object_id"], row_n["field_name"])
            key_r = (row_r["object_class"], row_r["object_id"], row_r["field_name"])
            if key_n != key_r:
                raise RuntimeError(f"satir {n_total}: dosyalar hizasiz ({key_n} != {key_r})")

            if not row_r["resolved_parent_match"]:
                hit = DUPLICATE_MAP.get(row_n["parent_name"])
                if hit is not None:
                    cid, cname = hit
                    row_r["resolved_parent_id"] = cid
                    row_r["resolved_parent_name"] = cname
                    row_r["resolved_parent_match"] = "match"
                    n_filled += 1

            writer.writerow(row_r)

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir     : {n_total:,}")
    print(f"dolan satir      : {n_filled:,}")


if __name__ == "__main__":
    main()
