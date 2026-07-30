# 29 Temmuz 2026 — sistem analizi: özet ve yol haritası

Tüm katmanların kod okuması + gerçek veri üzerinde ölçümle analizi.
Kapsam: 5.701 satır kaynak, 51 modül, 191 test (hepsi geçiyor),
231.291 kanonik kayıt.

## Dosyalar

| # | Rapor | Kapsam |
|---|---|---|
| [01](01_gate.md) | **gate/** | Aşama-1 deterministik triyaj |
| [02](02_ingest_ve_normalize.md) | **ingest/ + normalize/** | ham CSV → kanonik kayıt, Türkçe metin katmanı |
| [03](03_elastic_ve_embedding.md) | **elastic/ + embedding/** | index, mapping, arama, e5 vektörleri |
| [04](04_retrieve.md) | **retrieve/** | decompose (hipotez) + resolve (havuz + sinyaller) |
| [05](05_judge_ve_decide.md) | **judge/ + decide/** | LLM hakem, şema, hibrit yönlendirme |
| [06](06_eval_ve_batch.md) | **eval/** | üç batch türü, CSV mekaniği |
| [07](07_api_cli_config.md) | **api/ + cli/ + config** | arayüzler, job yönetimi, ayarlar |

Kanıt etiketleri: **[Ö]** ölçüldü/çalıştırıldı · **[K]** kod okumasıyla kesin ·
**[V]** muhakeme, ölçülmedi.

> **Revizyon 2026-07-29 (aynı gün, analizlerden sonra).** Kod bulgularının hiçbiri
> değişmedi; ölçüm durumu değişti:
> - v2'deki `real_labeled.csv` gold adayı **geçersiz çıktı ve silindi** → gold
>   sıfırdan üretilecek.
> - Önceki 50 sorguluk eval seti + deney script'leri scratchpad ile **silindi**.
> - Yerine `data/eval/benchmark_500_sample.csv` üretildi (500 sorgu, çok eksenli
>   kategorili, 39 doğrulanmış `no_match`).
> - DURUM §6d'nin "v2/v3 id uzayı uyuşmuyor" teşhisi **düzeltildi**: uzaylar aynı,
>   sorun `isimler_tekrarsız.csv`'nin `canonical_id` kolonunda.
> - "Eval setini repoya al" önerisi **geri çekildi** — gerçek affiliation kişisel
>   veri, `.gitignore` gereği commit edilmez.
> - `03` raporuna E9 eklendi (ES'te 3.7 GB v2 index artığı).
>
> Etkilenen bölümler: bu dosyada T4 + Dalga 0 · `01_gate` D + G6 · `06_eval` B5 ·
> `03_elastic` E9. Diğer raporlar (02/04/05/07) değişmedi.

---

## 1. Genel değerlendirme

Bu, **iyi bir kod tabanı.** Ayırt edici özelliği şu: neredeyse her tasarım
kararının arkasında yazılı, ölçülmüş bir gerekçe var — ve gerekçelerin çoğu
*reddedilen* alternatifi de anlatıyor. "Marker-regex neden olmadı", "bm25 neden
karardan çıktı", "P4 soft-exact neden rafa kalktı". Bu, kod tabanının kendi
kendini savunabilmesi demek ve nadirdir.

Tekrarlayan ve doğru olan ilke: **erken karar verme, kanıtı taşı.**
`decompose` sınır seçmez (5 hipotez), `resolve` RRF'yi tek skora ezdirmez (ham
sinyaller), `prompt` sorguyu ön-yapılandırmaz (ham metin).

Bulduğum sorunların çoğu "kötü kod" değil; **zincirin sonundaki tutarsızlıklar**:
taşınan kanıtın okunmaması, bir katmanda öğrenilen dersin komşu katmanda
uygulanmaması, ve kodun evrimini geriden takip eden docstring'ler.

---

## 2. Katmanlar arası dört tema

### T1 — Kanıt titizlikle taşınıyor, sonra okunmuyor

`ScoredCandidate` 9 sinyal taşıyor. Gate bunların **4'ünü hiç okumuyor**:
`hypotheses` (parent mutabakatı), `best_alias` (çapraz-dil köprüsü),
`passed_parent_filter`, `from_hypothesis_only`. Aynı desen judge'da: kosinüs
sorgu başına ekstra ES round-trip'iyle hesaplanıyor, 2026-07-27'de prompt'tan
çıkarıldı, ama hâlâ hesaplanıyor — artık hiçbir kararın girdisi değil.

→ `01_gate.md` B, `04_retrieve.md` E7, `05_judge_ve_decide.md` J6

### T2 — Aynı hata iki kez: "göreli skor" tuzağı

`bm25_norm` karardan çıkarıldı, gerekçe doğru ve ölçülüydü: *sorgu-içi göreli,
çöp aday da 1.0 alıp tabanı şişiriyor.* Ama `token_set_ratio` **aynı sınıftan**
ve bu fark edilmemiş — adayın token'ları sorgunun alt kümesiyse 100 döndürüyor:

```
sorgu: "calcutta institute of engineering and management ... kolkata india"
  aday "india"                          -> tsr = 100.0
  aday "indian institute of technology" -> tsr =  57.1
```

Sonuç: gate'in `no_match` kapısı fiilen ölü (baseline'da %2), review satırlarının
sinyalleri ve `confidence`'ı yanlış adaya bağlı. DURUM §6e'deki "tsr≥95 görünen 6
TUZAK" gözlemi muhtemelen bu.

→ `01_gate.md` A2, `04_retrieve.md` E5

### T3 — Config ile kod ayrışmış

`config/default.yaml` başlığı: *"okunmayan ölü anahtar bırakma (v2 O6 dersi)."*
Ölçüm: **9 anahtar hiç okunmuyor.** En zararlısı `retrieval.boosts` — v2
şemasından kalma, mapping'de var olmayan alan adları (`unit_name`,
`aliases.normalized`) ve koddakinden farklı değerler taşıyor. Burada boost
ayarlayan biri hiçbir etki göremez.

→ `07_api_cli_config.md` C1, `03_elastic_ve_embedding.md` E3

### T4 — Doğruluk HİÇ ölçülmemiş

- `decision.auto_precision_target: 0.98` bir hedef; ölçen kod yok (ve anahtar
  okunmuyor).
- **Gold YOK.** v2'deki `real_labeled.csv` denendi ve **kullanıcı tarafından
  geçersiz ilan edilip silindi** (2026-07-29) — eski ve yanlış etiketler. Gold
  sıfırdan üretilecek.
- Üç batch'in hiçbirinde `--gold-col` ya da skorlama yok.
- Üç batch'in ortak omurgası `csv_runner.py` **testsiz** — ve iki gerçek hatası
  orada.

**Regresyon seti ise ARTIK VAR** (2026-07-29): `data/eval/benchmark_500_sample.csv`
— 500 benzersiz sorgu, gerçek kaynaktan, çok eksenli kategorili
(`kurum_tipi`/`sorgu_formu`/`dil`/`bozulma`). 39 satırda doğrulanmış
`beklenen=no_match` var (katalogda karşılıkları olmadığı tek tek kontrol edildi) —
projedeki tek mevcut gold bu. Önceki 50 sorguluk set ve deney script'leri
scratchpad ile birlikte **silindi**, kurtarılamadı.

⚠️ Gerçek affiliation metinleri kişisel veri; `.gitignore` gereği **repoya
commit edilmez** (`data/eval/*_sample.csv`). Repoya giren şey kod ve toplu
metrikler, ham sorgular değil.

Bu, tüm serideki en önemli eksik: aşağıdaki önerilerin hiçbiri etkisi ölçülmeden
güvenle uygulanamaz.

→ `06_eval_ve_batch.md` B5/B7, `01_gate.md` D

---

## 3. Doğrulanmış hatalar (kanıtlı, spekülasyon değil)

| Sev | Bulgu | Nerede | Kanıt |
|---|---|---|---|
| 🔴 | `--limit N --resume` **hiç ilerlemiyor** — belgelenen parça-parça çalıştırma çalışmıyor | `eval/csv_runner.py` | çalıştırıldı: 2. koşu ok=0, skipped=3 |
| 🔴 | Embedding cache anahtarı **içerik değil id listesi** → parent adı değişince subunit vektörleri sessizce bayat kalır | `elastic/indexer.py` | kod |
| 🔴 | `token_set_ratio` alt-küme tuzağı → `no_match` kapısı ölü, review sinyalleri yanlış adayda, `confidence`=1.000 | `retrieve/resolve.py` → `gate/gate.py` | ölçüldü |
| 🟠 | `--resume` ile **tekrarlı sorgular sessizce düşüyor** → çıktı satır sayısı bayrağa göre değişiyor | `eval/csv_runner.py` | çalıştırıldı: 3 satır vs 2 satır |
| 🟠 | Üretim şeması pydantic şemasından **zayıf**: `{auto_match, matched_id:null}` üretilebiliyor ama reddediliyor | `judge/judge.py` ↔ `schema.py` | kod |
| 🟠 | LLM hatası, elde olan **gate cevabını da yok ediyor** (502 / exit 1) | `decide/decide.py` | kod |
| 🟠 | Vektör↔belge eşleşmesi iki fonksiyon arası **pozisyona** bağlı, tip korumasız | `elastic/indexer.py` | kod |
| 🟠 | "Sınır bulunamadı" ile "sorguda birim yok" **aynı değere çöküyor** → birim hiç aranmadan yok sayılıyor | `decompose` → `gate` | kod |
| 🟡 | `exact`in **ayırt ediciliği** ölçülmüyor, yalnız uzunluğu (`MIN_EXACT_SPAN=2`) | `gate/gate.py` | 6 tamamen-jenerik parent kaydı |
| 🟡 | `edge_ngram` indeksleniyor, **hiç sorgulanmıyor** (2 alan × 285K belge) | `mappings` ↔ `search` | grep |
| 🟡 | `resume` mevcut CSV başlığını **doğrulamıyor** → sessiz kolon kayması | `eval/csv_runner.py` | kod |
| 🟡 | `_trim` exact tavanı yok → %79 ad çakışması olan subunit korpusunda prompt şişip `num_ctx` aşabilir | `judge/candidates.py` | ölçüldü (%79) |
| 🟡 | `index_data(recreate=True)` **varsayılan** — yanlışlıkla çalıştırma index'i uçurur | `elastic/indexer.py` | kod |
| 🟡 | İki normalizasyon kanalı **apostrofta ayrışıyor** (1.692 kayıtta yalnız `s` token'i) | `normalize` ↔ ES analyzer | ölçüldü |
| 🟡 | Türkçe **stemmer yok** — morfoloji fuzzy'nin yan etkisiyle tesadüfen kısmen çalışıyor | `elastic/mappings.py` | kod |

---

## 4. Yol haritası

### Dalga 0 — Ölçüm belkemiği (önce bu; diğerlerinin ön koşulu)

*Revize 2026-07-29: regresyon seti çözüldü, gold hâlâ açık — sıra buna göre.*

1. **500 sorguyu `gate-batch`'ten geçir** → kategori kırılımlı baseline dağılımı +
   `auto_match` çıkan satırların listesi = **etiketleme kuyruğu**. Hiçbir karara
   bağlı değil, ~16 dk. (Regresyon izi burada kurulur; kayıp 50 sorguluk setin
   yerine geçer, 10 katı büyük.)
2. `csv_runner` testleri (**önce kırmızı**), sonra `--limit`/`--resume`/başlık
   düzeltmesi — büyük setin parça parça koşulabilmesi buna bağlı
3. **Gold üretimi (kritik yol, kullanıcı işi):** kuyruktaki auto satırlarını elle
   etiketle. `auto_precision` yalnız auto kovasından ölçüldüğü için 500'ün
   tamamı gerekmiyor — muhtemelen ~250 satır. 39 `no_match` satırı hazır geliyor.
4. `--gold-col` + skorlama (`auto_precision`, `auto_rate`, `no_match_recall`,
   kategori kırılımı)
5. `--gate-floor` (eşik süpürmesi bugün mümkün değil)

Darboğaz 3. madde. 1, 2, 4, 5 paralel gidebilir.

⚠️ **İstatistiksel sınır:** bu boyutta bir set `%98` hedefini *doğrulayamaz*,
yalnız felaketi yakalar (~250 auto kararında %95 güven aralığı geniş kalır).
Kurduğunuz şey **regresyon bekçisi**, sertifika değil. Gerçek doğrulama 500+
etiketli auto kararı ister — ama o etiketleme işi bu paketin çıktısı olan
araçla çok daha ucuzlar.

Bu paket olmadan aşağıdaki hiçbir maddenin etkisi bilinemez.

### Dalga 1 — Sessiz-yanlış riskleri (ucuz, yüksek değer)

5. Embedding cache anahtarına metin hash'i (1 satır)
6. Vektörü id-dict ile eşle (~10 satır)
7. `recreate` varsayılanı `False`
8. `resume` başlık doğrulaması
9. Judge şemasına çapraz-alan kısıtı (J1+J2)

### Dalga 2 — Karar kalitesi (ölçümle birlikte)

10. Gate: `confidence` tek formüle, `reason` ayrıştır, `no_match`'i LLM'den muaf tut
11. Korpus DF/IDF ile **ayırt edicilik** ölçüsü (`MIN_EXACT_SPAN`'in yerine) —
    elle stoplist değil, "veriye sor" ilkesine uygun
12. **Coverage** sinyali — #6 tsr-auto'nun `decompose` bağımlılığını ortadan
    kaldırır
13. `decide`'a gate-fallback politikası (J8)
14. Kullanılmayan kanıtı bağla: hipotez mutabakatı, `from_hypothesis_only`,
    `best_alias`

### Dalga 3 — Temizlik ve altyapı

15. Ölü config anahtarları: bağla ya da sil (özellikle `boosts`)
16. Kosinüs geri-doldurma yolunu kaldır (kararlarda kullanılmıyor)
17. `.edge` kararı: bağla ya da mapping'den kaldır
18. Job TTL + `DELETE /jobs/{id}`, chunk'lı yükleme, API'ye `resume`
19. `text_eski.py` sil, `is_evening` ya doldur ya sil
20. Stemmer + fuzziness daraltma **A/B deneyleri** (reindex gerekir)

---

## 5. Değiştirilmemesi gerekenler

Bu kararlar ölçülmüş ve doğru; tekrar açılmamalı:

- **decompose**: alt-dizge taraması + hipotez listesi (marker-regex'e ve tek sert
  sınıra dönülmemeli)
- **resolve**: recall-güvenli filtreli+filtresiz birleşim; RRF'nin yalnız
  havuzlama için kullanılması; ham sinyallerin korunması
- **elastic**: tek index + `record_type` filtresi (v2 IDF zehirlenmesi);
  `record_type:id` bileşik `_id` (55.431 çakışma); determinizm üçlüsü
- **gate**: exact-omurga; bm25/kosinüsün karardan çıkarılmış olması;
  `_enforce_coherence`'ın yalnız down-cap yapması
- **judge**: kısıtlı üretim + sentetik etiketler; `_trim`'in sırayı bozmaması;
  ham metin ilkesi; `num_ctx` + kırpılma tespiti; hataların yutulmaması
- **ingest**: P adımlarının sırası, P3'ün soyma-öncesi merge anahtarı ve
  alias-farkındalıklı muhafazakârlığı
- **eval**: satır-bazlı hata izolasyonu + progressive flush + `result_json`

Ve daha önce denenip reddedilenler (tekrar denenmemeli):
Gate #6 tsr-auto `institution_part` kilidiyle · P4 soft-exact elle stoplist ile ·
havuz-msearch birleştirmesi · Aşama-2 hakem · şema-fix.
