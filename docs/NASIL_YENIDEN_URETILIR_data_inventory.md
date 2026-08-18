# `data/inventory/` ara dosyaları — nasıl yeniden üretilir (2026-08-18)

Disk alanı için 3 büyük ara dosya silindi (~5GB). Hepsi script'lerle yeniden
üretilebilir, hiçbiri elle yapılan bir işi (LLM koşusu, insan düzeltmesi)
tekrarlamayı gerektirmiyor — sadece diskte duran veriyi tekrar hesaplıyorlar.

**Silinenler:** `normalized-backfilled.csv`, `resolved-llm-only.csv`,
`resolved-merged.csv`

**Silinmeyenler (kaynak/nihai, bunlar olmadan hiçbiri üretilemez):**
`raw.csv`, `normalized.csv`, `summary.csv`, `summary-yok-kaynakli.csv`,
`pasif-parent-kayitlari.csv`, `main_batch/temiz_sonuc.csv`,
`data/processed/parent_canonical.jsonl`

## Sırayla çalıştırma (repo kökünden)

```bash
# 1) normalized-backfilled.csv  (~1 dk)
#    girdi: data/inventory/normalized.csv
python3 scripts/backfill_parent_subunit_by_name.py

# 2) resolved-llm-only.csv  (~1 dk)
#    girdi: data/inventory/normalized.csv + main_batch/temiz_sonuc.csv
python3 scripts/merge_inventory_resolved.py

# 3) resolved-merged.csv  (~4-5 dk, 4 script sirayla)
#    her biri bir onceki adimin ciktisini isler:
python3 scripts/backfill_resolved_id_from_catalog_name.py
#    -> data/inventory/institution-field-inventory-resolved-catalog-backfilled.csv
python3 scripts/backfill_meb_askeri_manual.py
#    -> data/inventory/institution-field-inventory-resolved-final.csv
python3 scripts/backfill_rename_manual.py
#    -> data/inventory/institution-field-inventory-resolved-final2.csv
python3 scripts/backfill_duplicate_catalog_manual.py
#    -> data/inventory/resolved-merged.csv
```

**Önemli:** Adım 3'teki 4 script birbirinin çıktısını okuyor (zincir), bu
yüzden SIRAYLA çalıştırılmalı. Aralardaki 3 dosya
(`*-resolved-catalog-backfilled.csv`, `*-resolved-final.csv`,
`*-resolved-final2.csv`) otomatik üretilir ve zincir bitince silinebilir
(nihai olan sadece `resolved-merged.csv`).

`resolved-merged.csv` ve `normalized-backfilled.csv`'yi yeniden ürettikten
sonra, `summary.csv`/`summary-yok-kaynakli.csv`'yi de tekrar üretmek
istersen (örn. `subunit_match` kuralını değiştirdiysen):

```bash
python3 scripts/build_final_summary_csv.py
```

Bu, `data/inventory/summary.csv`'yi YENİDEN YAZAR — eğer elle bir düzeltme
yaptıysan önce yedekle.

## İlgili rapor
Tüm bu script'lerin NEDEN bu sırayla yazıldığı, hangi kararın hangi
gerekçeyle verildiği için: `docs/RAPOR_2026-08-18_envanter_parent_subunit_tamamlama.md`
(Bölüm B).
