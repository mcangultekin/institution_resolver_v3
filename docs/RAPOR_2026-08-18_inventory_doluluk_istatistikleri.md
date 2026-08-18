# institution-field-inventory doluluk istatistikleri (2026-08-18)

Toplam satır: **8.920.512**

Kaynak dosyalar:
- `institution-field-inventory-normalized.csv` (ham/kaynak)
- `institution-field-inventory-resolved.csv` (LLM/gate/judge batch çıktısı)
- `institution-field-inventory-normalized-backfilled.csv` (aynı `normalized_name`'in kaynakta dolu olan başka satırından kopyalama — `scripts/backfill_parent_subunit_by_name.py`)

## Parent

| | satır | oran |
|---|---:|---:|
| kaynakta zaten dolu | 4.596.039 | %51,5 |
| kaynakta boş (çözülmesi gereken) | 4.324.473 | %48,5 |
| ‑ LLM `match` (kataloğa eşleşti) | 1.392.048 | %15,6 |
| ‑ LLM `no_match` (eşleşme yok) | 327.864 | %3,7 |
| ‑ LLM `review` (kararsız) | 298.361 | %3,3 |
| ‑ LLM `judge_error` (hakem hatası) | 99.537 | %1,1 |
| ‑ **LLM toplam işlenen** | **2.117.810** | **%23,7** |
| ‑ backfill (aynı ad, kaynak kopyası) — parent+subunit doldu | 2.097.220 | %23,5 |
| ‑ backfill — sadece parent doldu (subunit belirsizdi) | 109.443 | %1,2 |
| ‑ **backfill toplam** | **2.206.663** | **%24,7** |
| **hâlâ tamamen boş** | **0** | **%0** |

Özet: kaynak + LLM-match + backfill = **8.194.750 satır (%91,9)** gerçek anlamda kurum (parent) bilgisine sahip.
Sonuçsuz kalan (`no_match` + `review` + `judge_error`) = **725.762 satır (%8,1)**.

## Subunit

Not: subunit'in kendi baseline'ı `parent_name`'den bağımsızdır — bir kurum bahsinde alt birim (fakülte/bölüm) hiç olmayabilir, bu normaldir.

| | satır | oran |
|---|---:|---:|
| kaynakta zaten dolu | 1.687.783 | %18,9 |
| kaynakta boş | 7.232.729 | %81,1 |
| ‑ LLM `match` | 388.885 | %4,4 |
| ‑ LLM `no_match` | 727.304 | %8,2 |
| ‑ LLM `review` | 485.098 | %5,4 |
| ‑ LLM `judge_error` | 99.520 | %1,1 |
| ‑ **LLM toplam işlenen** | **1.700.807** | **%19,1** |
| ‑ backfill (aynı ad, kaynak kopyası) ile dolan | 586.051 | %6,6 |
| ‑ **hâlâ boş** | **4.945.871** | **%55,4** |

### Parent ile subunit arasındaki fark neden büyük

1. **Backfill kapsamı dar**: subunit backfill'i sadece `parent_name` de kaynakta boş olan satırlarda (yani "hem parent hem subunit çözülmemiş" grupta, 2.206.663 satır) devreye girdi — bunun 586.051'inde subunit doldu. `parent_name` zaten kaynakta dolu olan ~4,6M satırda subunit hiç backfill edilmedi (script'in tetikleyicisi sadece `parent_name` boşluğu).
2. **LLM subunit'i daha az buluyor**: `no_match` oranı parent'ta %3,7 iken subunit'te %8,2 — çoğu kurum bahsinde belirlenebilir bir alt birim yok, bu beklenen bir durum.

## Backfill mantığı (özet)

`normalized_name` grubu içinde (parent_name doluysa):
- `parent_id`, `parent_name`, `parent_iz` grup içinde tutarlıysa (tek değer) → doldurulur.
- `subunit_name` de aynı grup içinde tutarlıysa → o da doldurulur; değilse (örn. büyük/küçük harf, virgül, kısaltma farkı — 104 grup) sadece parent doldurulur, subunit'e dokunulmaz.
- `subunit_id`, `subunit_iz` **hiçbir zaman** kopyalanmaz — bunlar satıra özel (kaynak sistemin o satıra verdiği kendi kayıt numarası gibi davranıyor), bir satırdan diğerine taşınamaz.
- Gerçekten çelişkili gruplar (aynı `normalized_name`, farklı `parent_id`/`parent_name`/`parent_iz` — 19 grup, örn. "institute of science" iki ayrı üniversiteye bağlı) tamamen atlanır, dokunulmaz.

İlgili scriptler: `scripts/backfill_parent_subunit_by_name.py`, `scripts/backfill_resolved_from_source_parent.py` (bu ikincisi resolved.csv üzerinde ayrı bir denemeydi, kullanılmadı).
