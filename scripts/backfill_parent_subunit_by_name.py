"""institution-field-inventory-normalized.csv icinde parent_name BOS olan
satirlari, AYNI normalized_name'e sahip BASKA satirlarda zaten DOLU olan
parent/subunit bilgisiyle doldurur. LLM/gate/judge YOK - sadece kaynakta
zaten cozulmus ayni-metin kayitlarindan kopyalama.

Neden guvenli:
  normalized_name grubu icinde (parent_name doluysa) parent_id/parent_name/
  parent_iz pratikte hep tutarli (tek deger) cikiyor. subunit_id ve
  subunit_iz satira ozel (kaynak sistemin o SATIRA verdigi kendi kayit
  numarasi gibi davraniyor) - bu ikisi asla baska bir satirdan
  kopyalanmiyor, bos birakiliyor.

  Grup icinde parent (id/name/iz) tutarli oldugu halde subunit_name farkli
  yazilmis olabilir (buyuk/kucuk harf, virgul, kisaltma vb. - orn. "Bartin
  Universitesi Egitim Fakultesi" vs "BARTIN ÜNİVERSİTESİ, EĞİTİM
  FAKÜLTESİ"). Bu durumda SADECE parent_id/parent_name/parent_iz doldurulur,
  subunit_name'e DOKUNULMAZ (hangi yazimin "doğru" oldugu belirsiz).

  parent_id/parent_name/parent_iz'in KENDISI farkli olan gruplar (ayni
  normalized_name, gercekten FARKLI kurumlar - orn. "institute of science"
  iki ayri universiteye bagli iki ayri kurum) TAMAMEN atlanir, hic
  dokunulmaz.

Cikti: orijinal dosyaya DOKUNULMAZ, ayri bir dosyaya yazilir:
  institution-field-inventory-normalized-backfilled.csv
Bu cikti, merge_inventory_resolved.py'nin girdisi olarak kullanilabilir -
parent_name artik dolu oldugu icin bu satirlar otomatik olarak "resolved_*
bos, arama yapilmadi" kuraliyla islenir (batch'e hic girmezler).

Kullanim:
    python3 scripts/backfill_parent_subunit_by_name.py
"""

from __future__ import annotations

import csv
from pathlib import Path

csv.field_size_limit(10_000_000)

NORMALIZED = Path("data/inventory/normalized.csv")
OUT = Path("data/inventory/normalized-backfilled.csv")

PARENT_COLS = ["parent_id", "parent_name", "parent_iz"]
FULL_COLS = PARENT_COLS + ["subunit_name"]


def _build_lookup() -> tuple[dict[str, tuple[str, str, str]], dict[str, str]]:
    """Doner: (parent_lookup, subunit_lookup).

    parent_lookup: normalized_name -> (parent_id, parent_name, parent_iz)
        parent (id/name/iz) grup icinde tutarliysa doldurulur.
    subunit_lookup: normalized_name -> subunit_name
        SADECE parent tutarliyken subunit_name de tutarliysa doldurulur.
        parent tutarli ama subunit farkliysa bu adin subunit_lookup'ta
        girisi olmaz (subunit'e dokunulmaz).
    """
    parent_vals: dict[str, set[tuple[str, str, str]]] = {}
    full_vals: dict[str, set[tuple[str, str, str, str]]] = {}
    with NORMALIZED.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row["parent_name"]:
                continue
            name = row["normalized_name"]
            parent_vals.setdefault(name, set()).add(tuple(row[c] for c in PARENT_COLS))
            full_vals.setdefault(name, set()).add(tuple(row[c] for c in FULL_COLS))

    parent_lookup = {n: next(iter(v)) for n, v in parent_vals.items() if len(v) == 1}
    n_real_conflict = sum(1 for v in parent_vals.values() if len(v) > 1)

    subunit_lookup: dict[str, str] = {}
    n_subunit_ambiguous = 0
    for n in parent_lookup:
        fv = full_vals[n]
        if len(fv) == 1:
            subunit_lookup[n] = next(iter(fv))[3]
        else:
            n_subunit_ambiguous += 1

    print(f"  -> dolu-parent_name goren {len(parent_vals):,} normalized_name")
    print(f"  -> {len(parent_lookup):,} parent tutarli -> parent_id/name/iz doldurulacak")
    print(f"     bunlarin {len(subunit_lookup):,} tanesinde subunit_name de tutarli -> o da doldurulacak")
    print(f"     {n_subunit_ambiguous:,} tanesinde subunit_name farkli yaziliyor -> subunit'e dokunulmuyor")
    print(f"  -> {n_real_conflict:,} gercek celiski (parent_id/name/iz farkli) -> tamamen atlandi")
    return parent_lookup, subunit_lookup


def main() -> None:
    print(f"kaynak parent/subunit sozlugu kuruluyor: {NORMALIZED}")
    parent_lookup, subunit_lookup = _build_lookup()

    n_total = 0
    n_target = 0  # parent_name bos olan satirlar
    n_filled_parent_only = 0
    n_filled_parent_and_subunit = 0

    with NORMALIZED.open(newline="", encoding="utf-8") as fin, \
         OUT.open("w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
        writer.writeheader()

        for row in reader:
            n_total += 1

            if not row["parent_name"]:
                n_target += 1
                name = row["normalized_name"]
                hit = parent_lookup.get(name)
                if hit is not None:
                    for col, val in zip(PARENT_COLS, hit):
                        row[col] = val
                    sub = subunit_lookup.get(name)
                    if sub is not None:
                        row["subunit_name"] = sub
                        n_filled_parent_and_subunit += 1
                    else:
                        n_filled_parent_only += 1
                    # subunit_id / subunit_iz BILEREK dokunulmuyor (satira ozel)

            writer.writerow(row)

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    n_filled = n_filled_parent_only + n_filled_parent_and_subunit
    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir                       : {n_total:,}")
    print(f"parent_name bos (hedef)            : {n_target:,}")
    print(f"  -> dolduruldu (toplam)           : {n_filled:,}")
    print(f"     - parent + subunit doldu      : {n_filled_parent_and_subunit:,}")
    print(f"     - sadece parent doldu         : {n_filled_parent_only:,}")
    print(f"  -> hala bos (celiski/yok)        : {n_target - n_filled:,}")


if __name__ == "__main__":
    main()
