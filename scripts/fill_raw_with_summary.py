"""raw.csv'nin bir kopyasini uretir; parent_name/subunit_name summary.csv'den
BASTAN doldurulur, eski parent_id/subunit_id old_* olarak korunur, summary'deki
id'ler new_* olarak eklenir. Orijinal raw.csv'ye DOKUNULMAZ.

raw.csv ve summary.csv satir-hizali (positional) uretilmistir (bkz.
scripts/build_final_summary_csv.py) - isimden sozluk kurmak yerine zip() ile
satir satir eslenir; her satirda current_institution_name karsilastirilarak
hizasizlik erken yakalanir.

Cikti kolonlari:
  object_class, object_id, field_name,
  current_institution_id, current_institution_name, current_institution_iz,
  current_institution_top_iz, current_institution_lvl,
  parent_id, new_parent_id, parent_name, parent_iz, parent_match,
  subunit_id, new_subunit_id, old_subunit_name, subunit_name, subunit_iz, subunit_match,
  source

old_subunit_name: raw.csv'nin ham (dokunulmamis) subunit_name'i. summary.csv
bu alani BILEREK ozumsemiyor (ham subunit kataloglarla hizali degil), bu
yuzden 1.687.783 satirin 1.687.721'inde (%99,996) resolved subunit_name bos
kaliyor - ham metin kaybolmasin diye ayri kolonda saklaniyor.

Kullanim:
    python3 scripts/fill_raw_with_summary.py
"""

from __future__ import annotations

import csv
from pathlib import Path

csv.field_size_limit(10_000_000)

RAW = Path("data/inventory/raw.csv")
SUMMARY = Path("data/inventory/summary.csv")
OUT = Path("data/inventory/raw-filled.csv")

OUT_FIELDS = [
    "object_class", "object_id", "field_name",
    "current_institution_id", "current_institution_name",
    "current_institution_iz", "current_institution_top_iz",
    "current_institution_lvl",
    "parent_id", "new_parent_id", "parent_name", "parent_iz", "parent_match",
    "subunit_id", "new_subunit_id", "old_subunit_name", "subunit_name", "subunit_iz", "subunit_match",
    "source",
]


def main() -> None:
    n_total = 0

    with RAW.open(newline="", encoding="utf-8") as fr, \
         SUMMARY.open(newline="", encoding="utf-8") as fs, \
         OUT.open("w", newline="", encoding="utf-8") as fout:
        reader_r = csv.DictReader(fr)
        reader_s = csv.DictReader(fs)
        writer = csv.DictWriter(fout, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for row_r, row_s in zip(reader_r, reader_s):
            n_total += 1

            if row_r["current_institution_name"] != row_s["current_institution_name"]:
                raise RuntimeError(
                    f"satir {n_total}: raw/summary hizasiz "
                    f"({row_r['current_institution_name']!r} != {row_s['current_institution_name']!r})"
                )

            writer.writerow({
                "object_class": row_r["object_class"],
                "object_id": row_r["object_id"],
                "field_name": row_r["field_name"],
                "current_institution_id": row_r["current_institution_id"],
                "current_institution_name": row_r["current_institution_name"],
                "current_institution_iz": row_r["current_institution_iz"],
                "current_institution_top_iz": row_r["current_institution_top_iz"],
                "current_institution_lvl": row_r["current_institution_lvl"],
                "parent_id": row_r["parent_id"],
                "new_parent_id": row_s["parent_id"],
                "parent_name": row_s["parent_name"],
                "parent_iz": row_r["parent_iz"],
                "parent_match": row_s["parent_match"],
                "subunit_id": row_r["subunit_id"],
                "new_subunit_id": row_s["subunit_id"],
                "old_subunit_name": row_r["subunit_name"],
                "subunit_name": row_s["subunit_name"],
                "subunit_iz": row_r["subunit_iz"],
                "subunit_match": row_s["subunit_match"],
                "source": row_s["kaynak"],
            })

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir: {n_total:,}")


if __name__ == "__main__":
    main()
