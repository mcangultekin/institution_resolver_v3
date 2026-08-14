"""Faz 0 olcum seti: `kaggle_judge_sonuc.csv`'den karar-tipi bazinda homojen ornek.

Kaggle kosusu (3.000 sorgu, envanter modu, gemma4:e4b) sistemin SU ANKI hali -
bu script ondan sabit bir olcum seti cikarir. Set, Faz 0'dan sonraki TUM
karsilastirmalarda ayni kalir (varyant A/B'leri, sema degisiklikleri, retrieval
duzeltmeleri) - olcumler arasi tutarlilik icin.

Ornekleme karar tipine gore HOMOJEN degil, kullanicinin verdigi kotalara gore
(2026-08-14): orantiliya yakin ama hata siniflari takviyeli. Orantili duz
ornekleme bu isi goremezdi - biçim hatasi havuzun %0,4'u, 120'lik bir orneklemde
0,4 satir duserdi.

Belirlenimci: sabit tohum + sinif icinde `query`'ye gore siralama. Ayni girdi
ayni cikti - script tekrar kosulunca ayni 120 sorgu secilir.

Kullanim:
    python3 scripts/build_faz0_sample.py
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)  # result_json kolonu uzun

SOURCE = Path("kaggle_judge_sonuc.csv")
OUT = Path("data/eval/faz0_ornek_125.csv")
SEED = 20260814

# (sinif adi, kota) - kullanici karari 2026-08-14.
# SIRA ONEMLI: tek bir RNG akisi siradan tuketiliyor, dolayisiyla listenin
# BASINA/ORTASINA sinif eklemek sonraki siniflarin secimini kaydirir. `review`
# sonradan eklendigi icin (kullanici atlamis) SONA konuldu - onceki 120'lik
# setin secimleri boylece birebir korundu.
QUOTAS: list[tuple[str, int]] = [
    ("auto_match", 68),
    ("no_match", 30),
    ("ambiguous", 5),
    ("uyusmazlik_hatasi", 12),
    ("bicim_hatasi", 5),
    ("review", 5),
]

# Olcum setinde tasinan kolonlar. Kaggle karari TABAN olarak tasinir
# (`kaggle_*` oneki) - yerel kosunun ciktisiyla karsilastirilacak olan bu.
FIELDNAMES = [
    "sinif",
    "agirlik",          # havuz / kota - sinif-ici olcumu havuza geri olceklemek icin
    "query",
    "normalized_name",  # envantere geri-join anahtari
    "rows",             # bu adin temsil ettigi envanter satiri sayisi (etki)
    # --- Kaggle (mevcut sistem) karari = taban ---
    "kaggle_status",
    "kaggle_parent_verdict",
    "kaggle_parent_id",
    "kaggle_parent_name",
    "kaggle_subunit_verdict",
    "kaggle_subunit_id",
    "kaggle_subunit_name",
    "kaggle_unit_phrase",
    "kaggle_error",
    "kaggle_judge_s",
    # --- gate (LLM'siz, deterministik) - bu ikisinin yerelde de AYNI cikmasi beklenir ---
    "gate_parent_verdict",
    "gate_subunit_verdict",
]


def classify(row: dict[str, str]) -> str | None:
    """Satiri olcum sinifina atar; sete girmeyecekse None."""
    if row["status"] == "error":
        err = row.get("error", "")
        if "uyuşmazlığı" in err:
            return "uyusmazlik_hatasi"
        if "biçim" in err:
            return "bicim_hatasi"
        return None
    # Karar siniflari: YALNIZ hakemin gercekten kosdugu satirlar (LLM katmanina odak).
    # judged=0 satirlarda karar gate'ten gelir - bu setin konusu degil.
    if row.get("judged") != "1":
        return None
    return row["parent_verdict"] or None


def main() -> None:
    if not SOURCE.exists():
        sys.exit(f"Kaynak yok: {SOURCE}")

    with SOURCE.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    buckets: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        c = classify(r)
        if c:
            buckets.setdefault(c, []).append(r)

    rng = random.Random(SEED)
    out_rows: list[dict[str, str]] = []
    print(f"Kaynak: {SOURCE} ({len(rows)} satir)\n")
    print(f"{'sinif':<20} {'havuz':>6} {'kota':>5} {'agirlik':>8}")
    print("-" * 42)

    for name, quota in QUOTAS:
        pool = sorted(buckets.get(name, []), key=lambda r: r["query"])  # belirlenimci taban
        if len(pool) < quota:
            print(f"UYARI: {name} havuzu {len(pool)}, kota {quota} - hepsi alindi")
            quota = len(pool)
        picked = rng.sample(pool, quota)
        weight = len(pool) / quota if quota else 0.0
        print(f"{name:<20} {len(pool):>6} {quota:>5} {weight:>8.1f}")
        for r in sorted(picked, key=lambda r: r["query"]):
            out_rows.append(
                {
                    "sinif": name,
                    "agirlik": f"{weight:.2f}",
                    "query": r["query"],
                    "normalized_name": r.get("normalized_name", ""),
                    "rows": r.get("rows", ""),
                    "kaggle_status": r["status"],
                    "kaggle_parent_verdict": r.get("parent_verdict", ""),
                    "kaggle_parent_id": r.get("parent_id", ""),
                    "kaggle_parent_name": r.get("parent_name", ""),
                    "kaggle_subunit_verdict": r.get("subunit_verdict", ""),
                    "kaggle_subunit_id": r.get("subunit_id", ""),
                    "kaggle_subunit_name": r.get("subunit_name", ""),
                    "kaggle_unit_phrase": r.get("unit_phrase", ""),
                    "kaggle_error": r.get("error", ""),
                    "kaggle_judge_s": r.get("judge_s", ""),
                    "gate_parent_verdict": r.get("gate_parent_verdict", ""),
                    "gate_subunit_verdict": r.get("gate_subunit_verdict", ""),
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(out_rows)

    print("-" * 42)
    print(f"{'TOPLAM':<20} {'':>6} {len(out_rows):>5}")
    print(f"\nCikti: {OUT}")

    # --- akil saglami kontrolleri ---
    queries = [r["query"] for r in out_rows]
    assert len(queries) == len(set(queries)), "tekrar eden sorgu var"
    etki = sum(int(r["rows"] or 0) for r in out_rows)
    print(f"Benzersiz sorgu: {len(set(queries))}")
    print(f"Temsil edilen envanter satiri: {etki:,}")


if __name__ == "__main__":
    main()
