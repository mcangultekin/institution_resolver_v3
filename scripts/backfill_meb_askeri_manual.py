"""87 eslesmeyen parent_name adindan iki grubu elle katalog id'sine baglar:

1) "TC MİLLİ EĞİTİM BAKANLIĞI <sehir/kampus>" (23 ad, 16.509 satir)
   -> sehir/kampus kismi ATILIR, hepsi tek bir kuruma baglanir:
      MEB (id 10740, parent_canonical.jsonl'deki ad: "Mi̇lli̇ Eği̇ti̇m Bakanliği")
   NOT: bu isim katalogda boyle (combining-dot artifact'li, "Bakanliği" not
   "Bakanlığı") kayitli - kataloğun kendi veri kalitesi sorunu, burada
   DUZELTILMEDI, oldugu gibi kullanildi.

2) 2016 sonrasi Milli Savunma Üniversitesi catisi altinda birlestirilen
   askeri egitim kurumlari (8 ad, 1.918 satir) -> MİLLİ SAVUNMA ÜNİVERSİTESİ
   (id 273): Kara/Deniz/Hava Harp Okulu Komutanligi, Genelkurmay Baskanligi,
   Deniz Kuvvetleri Komutanligi, Jandarma/Deniz Astsubay Meslek Yuksekokulu
   Komutanligi, Harp Akademileri Komutanligi.

Bu iki grubun DISINDA kalan 56 ad (kapatilan vakif universiteleri, bagimsiz
MYO'lar vb.) bu script'in kapsami disinda - dokunulmuyor.

Girdi: bir onceki adimin ciktisi
  institution-field-inventory-resolved-catalog-backfilled.csv
(isim-esleme ile %97,3'u zaten doldurulmus versiyon)
Kaynaktaki parent_name ise institution-field-inventory-normalized-backfilled.csv'den
okunur (hedef satirlari bulmak icin).

Cikti: institution-field-inventory-resolved-final.csv (yeni dosya, girdiler
DEGISTIRILMEZ).

Kullanim:
    python3 scripts/backfill_meb_askeri_manual.py
"""

from __future__ import annotations

import csv
from pathlib import Path

csv.field_size_limit(10_000_000)

NORMALIZED_BACKFILLED = Path("data/inventory/normalized-backfilled.csv")
RESOLVED_IN = Path("data/inventory/institution-field-inventory-resolved-catalog-backfilled.csv")
OUT = Path("data/inventory/institution-field-inventory-resolved-final.csv")

MEB_ID = "10740"
MEB_NAME = "Mi̇lli̇ Eği̇ti̇m Bakanliği"
MSU_ID = "273"
MSU_NAME = "MİLLİ SAVUNMA ÜNİVERSİTESİ"

MEB_NAMES = {
    "TC MİLLİ EĞİTİM BAKANLIĞI DİYARBAKIR",
    "TC MİLLİ EĞİTİM BAKANLIĞI GAZİANTEP",
    "TC MİLLİ EĞİTİM BAKANLIĞI KONYA",
    "TC MİLLİ EĞİTİM BAKANLIĞI NECATİBEY",
    "TC MİLLİ EĞİTİM BAKANLIĞI VAN",
    "TC MİLLİ EĞİTİM BAKANLIĞI İSTANBUL ATATÜRK",
    "TC MİLLİ EĞİTİM BAKANLIĞI İZMİR",
    "TC MİLLİ EĞİTİM BAKANLIĞI SAMSUN",
    "TC MİLLİ EĞİTİM BAKANLIĞI BURSA",
    "TC MİLLİ EĞİTİM BAKANLIĞI ERZURUM",
    "TC MİLLİ EĞİTİM BAKANLIĞI ESKİŞEHİR",
    "TC MİLLİ EĞİTİM BAKANLIĞI TRABZON",
    "TC MİLLİ EĞİTİM BAKANLIĞI AMASYA",
    "TC MİLLİ EĞİTİM BAKANLIĞI UŞAK",
    "TC MİLLİ EĞİTİM BAKANLIĞI ISPARTA",
    "TC MİLLİ EĞİTİM BAKANLIĞI BALIKESİR",
    "TC MİLLİ EĞİTİM BAKANLIĞI ÇANAKKALE",
    "TC MİLLİ EĞİTİM BAKANLIĞI KONYA SELÇUK",
    "TC MİLLİ EĞİTİM BAKANLIĞI EDİRNE",
    "TC MİLLİ EĞİTİM BAKANLIĞI GAZİ",
    "TC MİLLİ EĞİTİM BAKANLIĞI FATİH",
    "TC MİLLİ EĞİTİM BAKANLIĞI İZMİR BUCA",
    "TC MİLLİ EĞİTİM BAKANLIĞI DEMİRCİ",
}

ASKERI_NAMES = {
    "KARA HARP OKULU KOMUTANLIĞI",
    "DENİZ HARP OKULU KOMUTANLIĞI",
    "GENELKURMAY BAŞKANLIĞI",
    "DENİZ KUVVETLERİ KOMUTANLIĞI",
    "HAVA HARP OKULU KOMUTANLIĞI",
    "JANDARMA ASTSUBAY MESLEK YÜKSEKOKULU KOMUTANLIĞI",
    "DENİZ ASTSUBAY MESLEK YÜKSEKOKULU KOMUTANLIĞI",
    "HARP AKADEMİLERİ KOMUTANLIĞI",
}

MANUAL_MAP: dict[str, tuple[str, str]] = {}
for n in MEB_NAMES:
    MANUAL_MAP[n] = (MEB_ID, MEB_NAME)
for n in ASKERI_NAMES:
    MANUAL_MAP[n] = (MSU_ID, MSU_NAME)


def main() -> None:
    n_total = 0
    n_meb_filled = 0
    n_askeri_filled = 0

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
                hit = MANUAL_MAP.get(row_n["parent_name"])
                if hit is not None:
                    cid, cname = hit
                    row_r["resolved_parent_id"] = cid
                    row_r["resolved_parent_name"] = cname
                    row_r["resolved_parent_match"] = "match"
                    if cid == MEB_ID:
                        n_meb_filled += 1
                    else:
                        n_askeri_filled += 1

            writer.writerow(row_r)

            if n_total % 1_000_000 == 0:
                print(f"  ... {n_total:,} satir islendi")

    print(f"\nBITTI -> {OUT}")
    print(f"toplam satir           : {n_total:,}")
    print(f"MEB'e baglanan satir   : {n_meb_filled:,}")
    print(f"MSÜ'ye baglanan satir  : {n_askeri_filled:,}")


if __name__ == "__main__":
    main()
