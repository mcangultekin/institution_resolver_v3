"""Resolver'a hic girmemis (resolved_parent_match BOS) ama parent_name'i
(kaynaktan veya scripts/backfill_parent_subunit_by_name.py ile doldurulmus
olarak) DOLU olan satirlari, parent_canonical.jsonl ile ISIM eslesmesi
uzerinden dogrudan cozer - LLM/gate/judge YOK.

Neden guvenli:
  Bu satirlarin hepsinde toplam sadece 338 benzersiz parent_name metni var.
  Bunlarin 236'si, normalize edildiginde parent_canonical.jsonl'deki TEK bir
  kayda (canonical ad veya alias) birebir eslesiyor - "Aydin Adnan Menderes
  Universitesi" ile "Adnan Menderes Universitesi" gibi RENAME/kisaltma
  farklari degil, tam ayni yaziliş. Bu, LLM'in yaptigi bulanik/anlamsal
  eslestirmeden FARKLI ve daha guclu bir sinyal - tipografik/whitespace
  normalizasyonu disinda belirsizlik yok.

  15 ad DAHIL EDILMEDI - bunlar normalize edildiginde katalogda BIRDEN FAZLA
  farkli id'ye denk geliyor (ör. "SÜLEYMAN DEMİREL ÜNİVERSİTESİ" -> iki
  farkli id - katalogda muhtemelen mukerrer kayit var, bu script'in isi
  degil, ayri incelenmeli).

  87 ad (184k satir) hic eslesmiyor - bunlar ya yeniden adlandirilmis
  universiteler (alias eksik, catalog'a alias eklenmesi gerekiyor - ayri is),
  ya 2016 sonrasi kapatilan vakif universiteleri, ya da MEB il mudurlukleri/
  askeri kurumlar gibi kataloğun kapsami disindaki kurum tipleri. Bu script
  bunlara DOKUNMAZ.

Doldurulan sutunlar (institution-field-inventory-resolved.csv semantigiyle
AYNI - LLM'in 'match' sonucuyla ayni sekilde):
  resolved_parent_id   = katalogdaki id
  resolved_parent_name = katalogdaki canonical `name` (LLM-match satirlariyla
                          ayni konvansiyon - ham parent_name degil)
  resolved_parent_match = 'match'
Etiketle ayirt EDILMIYOR (kullanici tercihi) - bu satirlar diger LLM-match
satirlariyla ayni sekilde 'match' olarak isaretleniyor.

resolved_subunit_* sutunlarina DOKUNULMUYOR (bu script sadece parent icin).

Cikti: institution-field-inventory-resolved.csv'ye DOKUNULMAZ, ayri dosyaya
yazilir: institution-field-inventory-resolved-catalog-backfilled.csv

Kullanim:
    python3 scripts/backfill_resolved_id_from_catalog_name.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

csv.field_size_limit(10_000_000)
sys.path.insert(0, "src")

from institution_resolver_v3.normalize.query_pipeline import normalize  # noqa: E402

NORMALIZED_BACKFILLED = Path("data/inventory/normalized-backfilled.csv")
RESOLVED = Path("data/inventory/resolved-llm-only.csv")
CATALOG = Path("data/processed/parent_canonical.jsonl")
OUT = Path("data/inventory/institution-field-inventory-resolved-catalog-backfilled.csv")


def _build_catalog_lookup() -> dict[str, tuple[str, str]]:
    """normalize(ad/alias) -> (id, canonical_name). Coklu-id'ye denk gelenler DAHIL EDILMEZ."""
    raw: dict[str, set[tuple[str, str]]] = {}
    with CATALOG.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            pid, name = rec["id"], rec["name"]
            keys = {normalize(name).base, rec["normalized_name"]}
            for a in rec.get("aliases", []):
                v = a.get("value")
                if v:
                    keys.add(normalize(v).base)
            for k in keys:
                raw.setdefault(k, set()).add((pid, name))

    lookup: dict[str, tuple[str, str]] = {}
    n_ambiguous = 0
    for k, vals in raw.items():
        ids = {pid for pid, _ in vals}
        if len(ids) == 1:
            lookup[k] = next(iter(vals))
        else:
            n_ambiguous += 1
    print(f"  -> katalog: {len(lookup):,} tek-anlamli normalize anahtar")
    print(f"  -> {n_ambiguous:,} belirsiz (coklu id) anahtar - kullanilmiyor")
    return lookup


def main() -> None:
    print(f"katalog sozlugu kuruluyor: {CATALOG}")
    catalog_lookup = _build_catalog_lookup()

    # oncelikle 338 benzersiz parent_name'i tek tek normalize edip esle -
    # tum dosyayi normalize() ile taramaktansa cok daha hizli
    print(f"benzersiz parent_name -> katalog eslemesi kuruluyor: {NORMALIZED_BACKFILLED}")
    name_lookup: dict[str, tuple[str, str] | None] = {}

    n_total = 0
    n_target = 0
    n_filled = 0

    with NORMALIZED_BACKFILLED.open(newline="", encoding="utf-8") as fn, \
         RESOLVED.open(newline="", encoding="utf-8") as fr, \
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

            if not row_r["resolved_parent_match"] and row_n["parent_name"]:
                n_target += 1
                pname = row_n["parent_name"]
                if pname not in name_lookup:
                    name_lookup[pname] = catalog_lookup.get(normalize(pname).base)
                hit = name_lookup[pname]
                if hit is not None:
                    cid, cname = hit
                    row_r["resolved_parent_id"] = cid
                    row_r["resolved_parent_name"] = cname
                    row_r["resolved_parent_match"] = "match"
                    n_filled += 1

            writer.writerow(row_r)

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    n_unique_matched = sum(1 for v in name_lookup.values() if v is not None)
    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir                 : {n_total:,}")
    print(f"hedef (resolver'a girmemis + parent_name dolu): {n_target:,}")
    print(f"  -> katalogla eslesip dolduruldu             : {n_filled:,}")
    print(f"  -> hala islenmemis (87 eslesmeyen ad)        : {n_target - n_filled:,}")
    print(f"benzersiz parent_name adindan eslesen          : {n_unique_matched} / {len(name_lookup)}")


if __name__ == "__main__":
    main()
