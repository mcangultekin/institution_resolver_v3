"""Eslesmeyen 71 parent_name'den "rename" grubunu (25 ad, 156.404 satir)
elle katalog id'sine baglar - kullanicilar zamaninda kurumun ESKI/KISA
adiyla girilmis, kurum kataloğun icinde ama farkli (guncel) adla kayitli.

Dogrulama yontemi (kullanici onayli):
  23'u kataloğun kendi verisiyle dogrulandi (ya eski ad yeni adin bir alt-
  dizisi - "Aydin Adnan Menderes" icinde "Adnan Menderes" gibi - ya da
  kataloğun alias listesinde eski ad birebir geciyor, ör. id 80'in alias'i
  "Bülent Ecevit University, Zonguldak Karaelmas University").
  2 tanesi (İstanbul Bilim Üniversitesi -> Demiroğlu Bilim Üniversitesi,
  Anadolu Üniversitesi Eskişehir İktisadi ve Ticari İlimler Akademisi ->
  Anadolu Üniversitesi) kataloğun kendi verisinde iz birakmiyor, kullanici
  bunlarin dogrulugunu onayladi (2026-08-18).

Girdi: bir onceki adimin ciktisi
  institution-field-inventory-resolved-final.csv
(MEB + askeri manuel baglama tamamlanmis versiyon)

Cikti: institution-field-inventory-resolved-final2.csv (yeni dosya, girdi
DEGISTIRILMEZ).

Kullanim:
    python3 scripts/backfill_rename_manual.py
"""

from __future__ import annotations

import csv
from pathlib import Path

csv.field_size_limit(10_000_000)

NORMALIZED_BACKFILLED = Path("data/inventory/normalized-backfilled.csv")
RESOLVED_IN = Path("data/inventory/institution-field-inventory-resolved-final.csv")
OUT = Path("data/inventory/institution-field-inventory-resolved-final2.csv")

# eski_ad -> (katalog_id, katalog_adi)
RENAME_MAP: dict[str, tuple[str, str]] = {
    "ADNAN MENDERES ÜNİVERSİTESİ": ("113", "AYDIN ADNAN MENDERES ÜNİVERSİTESİ"),
    "ULUDAĞ ÜNİVERSİTESİ": ("365", "BURSA ULUDAĞ ÜNİVERSİTESİ"),
    "YÜZÜNCÜ YIL ÜNİVERSİTESİ": ("207", "VAN YÜZÜNCÜ YIL ÜNİVERSİTESİ"),
    "MUSTAFA KEMAL ÜNİVERSİTESİ": ("366", "HATAY MUSTAFA KEMAL ÜNİVERSİTESİ"),
    "CELÂL BAYAR ÜNİVERSİTESİ": ("1", "MANİSA CELÂL BAYAR ÜNİVERSİTESİ"),
    "GAZİOSMANPAŞA ÜNİVERSİTESİ": ("245", "TOKAT GAZİOSMANPAŞA ÜNİVERSİTESİ"),
    "NİĞDE ÜNİVERSİTESİ": ("188", "NİĞDE ÖMER HALİSDEMİR ÜNİVERSİTESİ"),
    "MİMAR SİNAN ÜNİVERSİTESİ": ("4", "MİMAR SİNAN GÜZEL SANATLAR ÜNİVERSİTESİ"),
    "OSMANGAZİ ÜNİVERSİTESİ": ("30", "ESKİŞEHİR OSMANGAZİ ÜNİVERSİTESİ"),
    "BİLECİK ÜNİVERSİTESİ": ("88", "BİLECİK ŞEYH EDEBALİ ÜNİVERSİTESİ"),
    "BEYKENT ÜNİVERSİTESİ": ("383", "İSTANBUL BEYKENT ÜNİVERSİTESİ"),
    "NİŞANTAŞI ÜNİVERSİTESİ": ("382", "İSTANBUL NİŞANTAŞI ÜNİVERSİTESİ"),
    "OKAN ÜNİVERSİTESİ": ("364", "İSTANBUL OKAN ÜNİVERSİTESİ"),
    "GEDİK ÜNİVERSİTESİ": ("21", "İSTANBUL GEDİK ÜNİVERSİTESİ"),
    "ACIBADEM ÜNİVERSİTESİ": ("40", "ACIBADEM MEHMET ALİ AYDINLAR ÜNİVERSİTESİ"),
    "TURGUT ÖZAL ÜNİVERSİTESİ": ("321", "MALATYA TURGUT ÖZAL ÜNİVERSİTESİ"),
    "BOZOK ÜNİVERSİTESİ": ("326", "YOZGAT BOZOK ÜNİVERSİTESİ"),
    "ZONGULDAK KARAELMAS ÜNİVERSİTESİ": ("80", "ZONGULDAK BÜLENT ECEVİT ÜNİVERSİTESİ"),
    "RİZE ÜNİVERSİTESİ": ("158", "RECEP TAYYİP ERDOĞAN ÜNİVERSİTESİ"),
    "TUNCELİ ÜNİVERSİTESİ": ("72", "MUNZUR ÜNİVERSİTESİ"),
    "GEBZE YÜKSEK TEKNOLOJİ ENSTİTÜSÜ": ("57", "GEBZE TEKNİK ÜNİVERSİTESİ"),
    "MUGLA UNIVERSITY": ("146", "MUĞLA SITKI KOÇMAN ÜNİVERSİTESİ"),
    "İSTANBUL AYVANSARAY ÜNİVERSİTESİ": ("378", "İSTANBUL TOPKAPI ÜNİVERSİTESİ"),
    "İSTANBUL BİLİM ÜNİVERSİTESİ": ("52", "DEMİROĞLU BİLİM ÜNİVERSİTESİ"),
    "ANADOLU ÜNİVERSİTESİ ESKİŞEHİR İKTİSADİ VE TİCARİ İLİMLER AKADEMİSİ": ("233", "ANADOLU ÜNİVERSİTESİ"),
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
                hit = RENAME_MAP.get(row_n["parent_name"])
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
