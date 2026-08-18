"""Iki yonlu envanter kosusunu birlestirir (Colab ters + Kaggle duz).

NEDEN AYRI BIR SCRIPT (2026-08-15): onceki `merge_judge_outputs.py` dosyalarin
AYRIK dilimler oldugunu varsayiyordu ve varsayim tutmadi - Kaggle bolunmemis
dosyayi kosmustu, yerel 1.002 satirin tamami onun icindeydi. Buradaki tasarim
karari: **ayriklik varsayilmaz, olculur.** Iki kosu ortada bulusup ust uste
binerse bu bir hata degil, sadece bosa harcanmis hesaptir; birlestirme
`query` uzerinden tekillestirir ve ortusmeyi RAPORLAR.

Hangi kopya tutulur: ikisi de ayni yapilandirmayi (v4 + `chosen` kapisi)
kullandigi icin fark etmez - `--tercih` ile secilebilir, varsayilan ilk dosya.
Yapilandirmalar AYNI DEGILSE script durur; sessizce karisik cikti uretmez.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(10_000_000)

TOPLAM = 143039


def _oku(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _yapilandirma(rows: list[dict]) -> set[tuple[str, str]]:
    """Kosunun (prompt_variant, pool_gate) imzalari - tek bir deger bekleriz."""
    return {(r.get("prompt_variant", ""), r.get("pool_gate", "")) for r in rows}


def birlestir(yollar: list[Path], tercih: int) -> tuple[list[dict], dict]:
    kaynaklar = [_oku(p) for p in yollar]

    imzalar = [_yapilandirma(r) for r in kaynaklar]
    for p, im in zip(yollar, imzalar):
        if len(im) > 1:
            sys.exit(f"{p}: tek dosya icinde KARISIK yapilandirma {im} - once ayirin")
    if len({next(iter(im)) for im in imzalar if im}) > 1:
        sys.exit(
            "Kosular farkli yapilandirmada uretilmis:\n"
            + "\n".join(f"  {p}: {im}" for p, im in zip(yollar, imzalar))
            + "\nBirlestirilemez - ayni prompt/kapi ile uretilmis olmalari gerekir."
        )

    birlesik: dict[str, dict] = {}
    nereden: dict[str, int] = {}
    ortusme = 0
    # tercih edilen dosya EN SONA konur ki uzerine yazsin
    sira = [i for i in range(len(kaynaklar)) if i != tercih] + [tercih]
    for i in sira:
        for r in kaynaklar[i]:
            q = r["query"]
            if q in birlesik:
                ortusme += 1
            birlesik[q] = r
            nereden[q] = i

    rapor = {
        "dosya_satir": {str(p): len(r) for p, r in zip(yollar, kaynaklar)},
        "tekil": len(birlesik),
        "ortusme": ortusme,
        "eksik": TOPLAM - len(birlesik),
        "kaynak_dagilimi": Counter(str(yollar[i]) for i in nereden.values()),
    }
    return list(birlesik.values()), rapor


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dosyalar", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, help="yazilacak birlesik CSV (yoksa sadece rapor)")
    ap.add_argument("--tercih", type=int, default=0,
                    help="cakismada hangi dosya kazansin (0=ilk, varsayilan)")
    a = ap.parse_args()

    for p in a.dosyalar:
        if not p.exists():
            sys.exit(f"yok: {p}")

    rows, rapor = birlestir(a.dosyalar, a.tercih)

    print("=" * 58)
    for p, n in rapor["dosya_satir"].items():
        print(f"  {n:>7,}  {p}")
    print("-" * 58)
    print(f"  {rapor['tekil']:>7,}  TEKIL sorgu")
    print(f"  {rapor['ortusme']:>7,}  ortusme (bosa harcanan hesap)")
    print(f"  {rapor['eksik']:>7,}  eksik  ({100*rapor['tekil']/TOPLAM:.1f}% kapsandi)")
    if rapor["ortusme"]:
        print("\n  -> Iki kosu ORTADA BULUSTU. Devam eden tarafi durdurun,")
        print("     her yeni satir artik tekrar.")
    if rapor["eksik"] <= 0:
        print("\n  -> TAM KAPSAMA.")
    print("=" * 58)

    if not a.out:
        return
    if not rows:
        sys.exit("yazilacak satir yok")
    # Kolonlarin birlesimi - kosular farkli surumde uretilmis olabilir
    alanlar = list(dict.fromkeys(k for r in rows for k in r))
    with a.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=alanlar)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows):,} satir -> {a.out}")


if __name__ == "__main__":
    main()
