# RAPOR — Envanter boru hattı: aşama aşama ölçülmüş istatistikler, öncesi/sonrası (2026-08-19)

Bu rapor `docs/RAPOR_2026-08-18_envanter_parent_subunit_tamamlama.md`'nin
yerine geçmez — o rapor tek oturumun teşhis/temizlik kronolojisiydi. Bu
rapor, boru hattının HER aşamasında dosyaları tek tek okuyup üretilen
**doğrudan ölçülmüş** (tahmini değil) sayıları, öncesi/sonrası karşılaştırmalı
şekilde sunar. Tüm sayılar bu oturumda `data/inventory/*.csv` ve
`main_batch/*.csv` dosyaları satır satır okunarak yeniden hesaplandı.

---

## Aşama 0 — Ham veri (`data/inventory/raw.csv` → normalize sonrası `normalized.csv`)

Toplam satır: **8.920.512**. Benzersiz `normalized_name`: **335.076**.

| alan | dolu | boş |
|---|---:|---:|
| `parent_name` | 4.596.039 (%51,5) | 4.324.473 (%48,5) |
| `subunit_name` | 1.687.783 (%18,9) | 7.232.729 (%81,1) |

`parent_name` boş olan 4.324.473 satırın arkasında **301.521 benzersiz
`normalized_name`** var — yani aynı kurum adı binlerce kez tekrar ediyor
(duplicate), sorgulanması gereken gerçek "farklı isim" sayısı çok daha az.

---

## Aşama 1 — Dedup: 286.948 sorguluk havuz (`data/jobs/batch_input_parent_empty.csv`)

301.521 benzersiz boş-parent adından **286.948'i** (query, normalized_name,
rows, raw_variants, source_ids, top_object_class, legacy_conflict kolonlarıyla)
tekilleştirilip sorgu havuzuna alındı.

**Kapsam açığı (o an fark edilmedi):** 301.521 − 286.948 ≈ **14.573 ad hiç
kuyruğa girmedi.** Bu, Aşama 5'te geri satır düzeyinde 2.206.663 satırlık bir
boşluk olarak ortaya çıkacak (bkz. aşağı).

---

## Aşama 2 — Gate-only batch (LLM'siz) → `main_batch/gate_batch_inventory.csv`

286.948 sorgunun tamamı `status=ok`.

| `parent_verdict` | sorgu |
|---|---:|
| `auto_match` | 132.336 |
| `review` | 121.351 |
| `ambiguous` | 21.688 |
| `no_match` | 11.573 |

`needs_review` bayrağı: **0 → 143.909** sorguda gate tek başına nihai karar
verdi (auto_match+no_match); **1 → 143.039** sorgu hakeme (LLM) kaldı.

---

## Aşama 3 — LLM hakem batch'i (Colab + Kaggle, V4EC) → `main_batch/birlesik_v4ec_duzeltilmis.csv`

Girdi: `needs_review_subset.csv`, **143.039** sorgu (Colab ve Kaggle'da ayrı
uçlardan koşulup birleştirildi + elle düzeltme).

| `status` | sorgu |
|---|---:|
| `ok` | 125.203 |
| `error` (hakem geçersiz cevap verdi → karar YOK) | 17.836 |

---

## Aşama 4 — Gate + hakem birleşimi → `main_batch/temiz_sonuc.csv`

286.948 sorgu için TEK nihai karar (`scripts/temiz_batch_olustur.py`):
gate'in `needs_review=0` dediği 143.909'da gate kararı, `needs_review=1`
dediği 143.039'da hakem kararı kullanıldı.

| `parent_match` | sorgu | oran |
|---|---:|---:|
| `match` | 159.909 | %55,7 |
| `no_match` | 56.137 | %19,6 |
| `review` | 53.066 | %18,5 |
| `judge_error` | 17.836 | %6,2 |

(132.336 gate auto_match + 27.573 hakem auto_match = 159.909 ✓)

---

## Aşama 5 — Sorgu kararlarının 4.324.473 boş satıra uygulanması (join)

`temiz_sonuc.csv`'deki 286.948 karar, `normalized_name` üzerinden Aşama 0'daki
4.324.473 boş-parent satırına join edildi (ölçüm: bu oturumda gerçek join
çalıştırılarak doğrulandı).

| | satır |
|---|---:|
| kararı bulunan (kuyruğa girmiş adlar) | **2.117.810** (%49,0) |
| kararı bulunmayan (Aşama 1'de kuyruğa hiç girmemiş 14.591 ad) | **2.206.663** (%51,0) |

Kararı bulunan 2.117.810 satırın dağılımı (satır düzeyinde, sorgu düzeyinden
farklı — çünkü her ad farklı sayıda satırı temsil ediyor):

| `parent_match` | satır |
|---|---:|
| `match` | 1.392.048 |
| `no_match` | 327.864 |
| `review` | 298.361 |
| `judge_error` | 99.537 |

**Bu aşamada fark edilen kusur:** gate+hakem'in kapsadığı 2,1M satır dışında
kalan 2,2M satır (%51'i!) hâlâ tamamen boştu — çünkü 14.591 ad hiç
sorgulanmamıştı. Bu, "LLM/gate batch = çözüm" varsayımının satır bazında
yeterli olmadığını gösterdi.

---

## Aşama 6 — Duplicate-tabanlı backfill (kullanıcının bahsettiği adım)

`scripts/backfill_parent_subunit_by_name.py`: LLM/gate'e hiç sorulmayan
2.206.663 satır için, **aynı `normalized_name` grubu içinde** (kaynakta o
addan başka satırlarda) `parent_name`/`parent_id`/`parent_iz` zaten doluysa
ve grup içinde tutarlıysa, o değer kopyalanarak boş satırlar dolduruldu.
Mantık: aynı kurum adı zaten 8,9M satırlık kaynağın başka bir yerinde
(farklı obje/kayıt) parent bilgisiyle birlikte geçiyorsa, bu bilgi güvenle
taşınabilir; sadece `subunit_id`/`subunit_iz` (satıra özel kayıt no'su gibi
davrandığı için) hiç kopyalanmadı.

| | satır |
|---|---:|
| backfill ile **parent+subunit** birlikte dolan | 2.097.220 |
| backfill ile **sadece parent** dolan (grup içinde subunit adı tutarsızdı — 104 grup, örn. büyük/küçük harf farkı) | 109.443 |
| **backfill toplamı** | **2.206.663** |
| gerçek çelişkili grup, dokunulmadı (19 grup, aynı ad farklı gerçek kurum) | 0 (atlandı) |

**Doğrulama (aritmetik kapanış):**
4.596.039 (kaynakta zaten dolu) + 2.117.810 (LLM/gate işlendi) + 2.206.663
(backfill) = **8.920.512** — toplam satır sayısına tam eşit. Yani Aşama 6
sonunda `parent_name` sütunu satır düzeyinde **%0 boş** kaldı (%48,5 → %0).

---

## Aşama 7 — Kataloğa isim eşleme + elle düzeltme

Parent'ı (ham veya backfill ile) dolu olan satırlardaki **338 benzersiz ad**,
`data/processed/parent_canonical.jsonl` kataloğuyla eşleştirildi:

| | ad | satır |
|---|---:|---:|
| kataloğa birebir tek eşleşti | 236 | 6.481.495 |
| katalogda iki farklı id'ye denk geldi → YÖK-referanslı id seçildi | 15 | 137.090 |
| hiç eşleşmedi → elle bağlandı (MEB 23 ad / askeri 8 ad / rename 25 ad) | 56 | 174.831 |

Katalog eşleşme oranı: **%97,3 → %99,86**.

---

## Aşama 8 — Nihai `summary.csv` (8.920.512 satır)

| `parent_match` | satır | oran |
|---|---:|---:|
| `match` | 8.185.464 | %91,8 |
| `no_match` | 327.864 | %3,7 |
| `review` | 307.647 | %3,4 |
| `judge_error` | 99.537 | %1,1 |

| `subunit_match` | satır | oran |
|---|---:|---:|
| `yok` (subunit yok, normal) | 5.410.872 | %60,7 |
| `review` | 2.293.739 | %25,7 |
| `no_match` | 727.417 | %8,2 |
| `match` | 388.947 | %4,4 |
| `judge_error` | 99.537 | %1,1 |

`kaynak` (katalog referans tipi): `yok` (YÖK) 7.465.503 · `ror` 719.961 ·
boş (eşleşmeyen 9.286 + `no_match`/`review`/`judge_error` grubu) 735.048.

---

## Öncesi/sonrası özet tablosu

| Metrik | Ham veri (Aşama 0) | Nihai (`summary.csv`) |
|---|---:|---:|
| Parent bilgisi taşıyan satır | 4.596.039 (%51,5) | 8.513.328 = match+backfill'in kataloğa bağlanan kısmı ≈ **8.185.464 (%91,8)** kataloğa çözülmüş |
| Parent tamamen boş satır | 4.324.473 (%48,5) | **0 (%0)** ham alan düzeyinde; katalog `match` olmayan (`no_match`+`review`+`judge_error`) = 735.048 (%8,2) |
| Subunit bilgisi taşıyan satır | 1.687.783 (%18,9) | `match`(388.947)+`review`(2.293.739, %79'u ham veride zaten dolu ama kural gereği kullanılmadı) |
| Katalog id kapsamı (338 ad üzerinden) | — | %97,3 → %99,86 (elle düzeltmeyle) |
| Kapsam dışı kalan satır | 4.324.473 sorgulanmamış | 9.286 (%0,14) — kapanmış vakıf üniv. / bağımsız MYO |

**Zincirin en kritik adımı Aşama 6 (duplicate backfill)** oldu: gate+LLM
batch'i tek başına satırların yalnız %49'unu (2,1M/4,3M) kapatabiliyordu,
çünkü dedup sırasında 14.591 ad kuyruğa hiç girmemişti (Aşama 1'deki sessiz
kapsam açığı). Aynı ada ait başka satırlarda zaten var olan bilgiyi
kopyalayan backfill, kalan %51'i (2,2M satır) LLM'e hiç sormadan, ücretsiz
şekilde kapattı.

## İlgili
`docs/RAPOR_2026-08-18_envanter_parent_subunit_tamamlama.md` (aynı işin
teşhis/temizlik/dosya-yapısı anlatımı), `docs/RAPOR_2026-08-18_inventory_doluluk_istatistikleri.md`
(bu raporun Aşama 0/5/6 sayılarının ilk hâli), `docs/NASIL_YENIDEN_URETILIR_data_inventory.md`
(script çalıştırma sırası).
